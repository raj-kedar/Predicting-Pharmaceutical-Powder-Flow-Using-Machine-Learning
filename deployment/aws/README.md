# Deploying FlowLytix on AWS

One EC2 server runs Caddy (HTTPS) in front of the FlowLytix container. Data lives in
Amazon RDS PostgreSQL. Visitors use `https://<elastic-ip>` with no domain name needed.

```text
Browser ──HTTPS──> Elastic IP ──> EC2 t3.small ┬─ Caddy (Let's Encrypt IP certificate)
                                               └─ FlowLytix API + frontend
                                                       │ private network, TLS
                                                       └──> RDS PostgreSQL
Image: private ECR repository ── pulled with the server's IAM role (no keys on the server)
```

| File | Purpose |
|---|---|
| `push-image.ps1` | Builds the image on your PC and pushes it to private ECR |
| `make-user-data.ps1` | Creates `out/user-data.sh` to paste when launching EC2 |
| `server/docker-compose.yml` | Production stack: Caddy + API, locked down |
| `server/Caddyfile.ip` | HTTPS on the bare IP (main option) |
| `server/Caddyfile.sslip` | HTTPS on `<ip>.sslip.io` (backup option) |
| `server/deploy.sh` | Pulls the image and starts or updates the app on the server |

Never paste passwords, AWS keys or Razorpay keys into chat, email or this repository.

---

## 0. Before you start

- Get your own IAM Identity Center or IAM user from the account owner, with MFA.
- Pick one region and use it everywhere, for example **Asia Pacific (Mumbai) `ap-south-1`**.
- In **Billing and Cost Management > Budgets**, create a monthly cost budget of about **USD 5**
  with email alerts to both of you.
- Check the free plan's credit balance and expiry under **Billing > Credits**.

## 1. Install the AWS CLI on your PC (one time)

1. Download and install the official AWS CLI v2 for Windows from
   <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>.
2. Sign in with temporary credentials (choose the region from step 0):

```powershell
aws configure sso --profile flowlytix
```

```powershell
aws sso login --profile flowlytix
```

If the account owner gave you IAM access keys instead, use `aws configure --profile flowlytix`.

## 2. Push the image to ECR

Start Docker Desktop, then from the `powder-flow` folder:

```powershell
.\deployment\aws\push-image.ps1 -Region ap-south-1 -Profile flowlytix
```

It creates a private repository named `flowlytix` (scan on push, keeps the newest 3 images),
builds, pushes, and prints the **image URI**. Copy it for later steps.

## 3. Create the server role (IAM)

**IAM > Roles > Create role** > Trusted entity **AWS service**, use case **EC2**. Attach:

- `AmazonSSMManagedInstanceCore` (browser terminal, no SSH keys)
- `AmazonEC2ContainerRegistryReadOnly` (pull the image)

Name it `flowlytix-ec2`. After step 5b, add the inline S3 policy shown there.

## 4. Create two security groups

**EC2 > Security Groups > Create** in the default VPC:

| Name | Inbound rules |
|---|---|
| `flowlytix-web` | HTTP 80 from `0.0.0.0/0` and `::/0`; HTTPS 443 from `0.0.0.0/0` and `::/0`. **No SSH.** |
| `flowlytix-db` | PostgreSQL 5432 from source **`flowlytix-web`** (the group, not an IP) |

Port 80 must stay open: Let's Encrypt uses it to issue and renew the certificate.

## 5. Create the database (RDS PostgreSQL)

**RDS > Create database**:

| Setting | Value |
|---|---|
| Method | Standard create |
| Engine | PostgreSQL 16 |
| Template | **Free tier** (if offered) |
| Instance | `db.t4g.micro` or `db.t3.micro` |
| Storage | 20 GiB gp3, **storage autoscaling off** |
| DB identifier | `flowlytix-db` |
| Master username | `flowlytix` |
| Password | Self managed. **Letters and digits only**, 24+ characters |
| Public access | **No** |
| VPC security group | `flowlytix-db` only (remove `default`) |
| Initial database name | `flowlytix` (under Additional configuration) |
| Backups | Automated, 1 day (the maximum on the AWS Free plan) |
| Encryption | Enabled |
| Deletion protection | Enabled |
| Performance Insights / Enhanced monitoring | Off |

When it is available, copy the **Endpoint**. Your connection string is:

```text
postgresql+psycopg://flowlytix:PASSWORD@ENDPOINT:5432/flowlytix?sslmode=require
```

Secrets Manager is not needed and costs extra. The password goes only in the server's `.env`.

## 5b. Create the private photo bucket (S3)

**S3 > Create bucket** in the same region:

| Setting | Value |
|---|---|
| Name | globally unique, for example `flowlytix-photos-<random digits>` |
| Object Ownership | ACLs disabled (bucket owner enforced) |
| Block all public access | **On** (all four boxes) |
| Versioning | Off |
| Default encryption | SSE-S3 |

Then **IAM > Roles > flowlytix-ec2 > Add permissions > Create inline policy > JSON**, replacing
`BUCKET` with your bucket name, and name it `flowlytix-photos`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": [
      "arn:aws:s3:::BUCKET/profile/*",
      "arn:aws:s3:::BUCKET/site/*"
    ]
  }, {
    "Effect": "Allow",
    "Action": "s3:ListBucket",
    "Resource": "arn:aws:s3:::BUCKET"
  }]
}
```

The server can only change photo files and cannot delete the bucket. The list permission lets
S3 report a missing photo as "not found" instead of "access denied". Nothing in it is public. The app serves each photo itself after checking who is asking.

## 6. Allocate an Elastic IP

**EC2 > Elastic IPs > Allocate**. Note the address. One IP **attached to a running server**
is covered by the free 750 hours; an unattached one is charged.

## 7. Generate the server setup script

```powershell
.\deployment\aws\make-user-data.ps1 -ImageUri <image URI from step 2>
```

This writes `deployment\aws\out\user-data.sh`. Use `-SiteMode sslip` only for the backup option.

## 8. Launch the server

**EC2 > Launch instance**:

| Setting | Value |
|---|---|
| Name | `flowlytix` |
| Image | **Ubuntu Server 24.04 LTS, 64-bit (x86)** |
| Type | **t3.small** (or t3.micro) |
| Key pair | **Proceed without a key pair** (we use Session Manager) |
| Network | Default VPC, auto-assign public IP **on**, security group `flowlytix-web` |
| Storage | 20 GiB gp3, encrypted |
| Advanced > IAM instance profile | `flowlytix-ec2` |
| Advanced > Metadata version | **V2 only (token required)** |
| Advanced > Metadata response hop limit | **2** (lets the app container use the role for S3) |
| Advanced > User data | Paste the whole of `out/user-data.sh` |

Then **Elastic IPs > select yours > Associate** with the `flowlytix` instance.

## 9. Configure and start

**EC2 > select the instance > Connect > Session Manager > Connect.** In the browser terminal:

```bash
sudo tail -n 5 /var/log/flowlytix-setup.log
```

Wait for "FlowLytix setup finished" (2–5 minutes after launch). Then add the database URL
and Razorpay keys:

```bash
sudo nano /opt/flowlytix/.env
```

Save with Ctrl+O, Enter, Ctrl+X. Start the app:

```bash
sudo /opt/flowlytix/deploy.sh
```

Watch the certificate being issued (usually under a minute):

```bash
sudo docker compose -f /opt/flowlytix/docker-compose.yml logs -f caddy
```

Open `https://<elastic-ip>/`. The browser should show a padlock with no warning.

**If the IP certificate fails**, switch to the backup and redeploy:

```bash
sudo sed -i 's/^SITE_MODE=.*/SITE_MODE=sslip/' /opt/flowlytix/.env && sudo /opt/flowlytix/deploy.sh
```

Do not retry the IP certificate many times in a row; Let's Encrypt limits failed attempts.

## 10. Create the first accounts

```bash
sudo docker compose -f /opt/flowlytix/docker-compose.yml exec api python -m scripts.seed
```

It prints three passwords **once**. Sign in at `https://<elastic-ip>/admin`, then change each
password under **My account**. Later accounts are created in the admin panel or by sign-up.

The seed creates the **superadmin** `owner@example.com` (the only role that can edit the
public website and manage other superadmins). Every printed password is temporary: the app
forces a new password at first sign-in, before anything else can be used.

To choose the superadmin's first-time password yourself instead of the printed one (type it
here only, never in chat or files):

```bash
sudo docker compose -f /opt/flowlytix/docker-compose.yml exec api python -m scripts.make_superadmin owner@example.com --temporary-password 'YOUR-TEMPORARY-PASSWORD'
```

Sign in at `https://<your address>/admin` straight away and set a strong private password.
Until you do, anyone who knows the temporary password could take the account. There is
deliberately no web page that creates or promotes superadmins.

## 11. Connect Razorpay

In the Razorpay Dashboard (Live mode needs completed KYC):

1. **Account & Settings > API Keys**: generate keys, put them in `.env` as `RAZORPAY_KEY_ID`
   and `RAZORPAY_KEY_SECRET`.
2. **Account & Settings > Webhooks > Add**: URL `https://<your address>/billing/webhook`,
   event **payment.captured**, a strong secret, then put that secret in `.env` as
   `RAZORPAY_WEBHOOK_SECRET`.
3. Set **Payment capture** to automatic if offered (FlowLytix also captures if needed).
4. Run `sudo /opt/flowlytix/deploy.sh`, then make one small real purchase and confirm it in
   the admin panel under **Payments**.

Razorpay reviews the website during activation. Fill in the business details in
`app/src/content.ts` first, then push a new image. If Razorpay does not accept an IP address
as the website or webhook URL, use the sslip backup address.

## 12. Updating the app

```powershell
.\deployment\aws\push-image.ps1 -Region ap-south-1 -Profile flowlytix
```

Then on the server, set the new tag and redeploy:

```bash
sudo nano /opt/flowlytix/.env
```

```bash
sudo /opt/flowlytix/deploy.sh
```

## 12b. Stop and start from the AWS dashboard

Open **CloudWatch > Dashboards > FlowLytix-Control** in Mumbai. If AWS asks to allow the custom
widget, choose **Allow always**. Then use **Stop FlowLytix**, **Start FlowLytix** and **Refresh**.

A Lambda function (`flowlytix-power`) runs a safe step every 5 minutes: it stops the server and
then the database, or starts the database and then the server. Allow about 15 minutes. While
stopped, it also re-stops the database after AWS's automatic 7-day restart.

Use the dashboard rather than the EC2 or RDS pages: while the mode is Stopped, anything started
by hand is stopped again. The function can only start and stop these two resources; it cannot
terminate or delete anything. Install or update it with `.\deployment\aws\setup-power.ps1`.

## 13. Backups

On the AWS Free plan, RDS keeps 1 day of automatic backups. Before any major change or demonstration, take a manual snapshot:
**RDS > flowlytix-db > Actions > Take snapshot**.

## 14. Costs to watch

| Item | Note |
|---|---|
| EC2 t3.small | Free-plan eligible; one server only (750 hours per month are shared) |
| Elastic IP | Free while attached to a running server, charged when unattached |
| RDS + 20 GB | Paid from credits; check the free plan covers your instance class |
| ECR, EBS, snapshots | Small; paid from credits |
| S3 photos | A few MB; photos are re-encoded to about 30–60 KB each |
| Avoid | Load balancer, NAT gateway, second server, Multi-AZ RDS, Secrets Manager |

## 15. Shutting everything down

In this order, so nothing keeps billing:

1. **EC2**: terminate the `flowlytix` instance (its disk is deleted with it).
2. **Elastic IPs**: **release** the address.
3. **RDS**: disable deletion protection, then delete `flowlytix-db` (take a final snapshot
   only if you need the data, and delete it later).
4. **ECR**: delete the `flowlytix` repository. **S3**: empty, then delete the photo bucket.
5. Delete the `flowlytix-web` and `flowlytix-db` security groups and the `flowlytix-ec2` role.
6. **Razorpay**: delete the webhook and API keys.
7. Next day, check **Billing > Bills** shows no running charges.

## Troubleshooting

| Symptom | Check |
|---|---|
| Session Manager has no Connect button | Role `flowlytix-ec2` attached? Wait 5 minutes after launch |
| `deploy.sh`: no public IPv4 | Associate the Elastic IP first |
| Image pull denied | Role has `AmazonEC2ContainerRegistryReadOnly`; image URI and region match |
| `/ready` shows database false | RDS endpoint and password in `.env`; `flowlytix-db` allows 5432 from `flowlytix-web` |
| Browser certificate warning | `logs caddy`; ports 80/443 open; switch to the sslip backup |
| Server slow or out of memory | Use t3.small; the setup adds 2 GB swap |
| Photo upload says storage unavailable | Bucket name and `AWS_REGION` in `.env`; inline S3 policy on the role; metadata hop limit 2 |
