# Predicting-Pharmaceutical-Powder-Flow-Using-Machine-Learning
Pharmaceutical powder flowability classification using real laboratory data and machine learning, with explainable AI and AWS/Azure deployment. For a real world use Industry

> **Status:** Repository structure and branch workflow set up. Sections marked _TBD_ are filled in as the project progresses.

## Project Overview
Machine-learning system that classifies the **flowability class** of pharmaceutical powders (excipients and API granules) from real laboratory measurements. See [docs/project_overview.md](docs/project_overview.md).

## Problem Statement
Flowability testing is time- and material-intensive. This project predicts the flowability class from measurable powder properties. See [docs/problem_statement.md](docs/problem_statement.md).

## Objectives
- Build a reproducible ML pipeline on real laboratory data.
- Compare multiple classifiers and select a final model.
- Explain predictions with explainable AI (XAI).
- Deploy the final model to AWS or Azure.

## Real Laboratory Dataset
_TBD_ — see [docs/dataset_description.md](docs/dataset_description.md). Raw data in `data/raw/` is **immutable** and is not committed to Git.

## Input Features
_TBD_ — see [data/metadata/feature_dictionary.csv](data/metadata/feature_dictionary.csv) and [docs/feature_description.md](docs/feature_description.md).

## Target Classes
Multiclass flowability classification. Reference scale: [data/metadata/class_definitions.csv](data/metadata/class_definitions.csv) (to be confirmed against the lab protocol).

## Methodology
Data inspection → EDA → cleaning → feature engineering → class distribution analysis → target-leakage check → training → comparison → tuning → explainability → final model. See [docs/machine_learning_methodology.md](docs/machine_learning_methodology.md).

## Models Used
Candidates: Logistic Regression, Random Forest, SVM, KNN, XGBoost, and other suitable classifiers. See [docs/model_selection.md](docs/model_selection.md).

## Evaluation Metrics
Accuracy, precision, recall, F1-score (macro/weighted), confusion matrix and multiclass metrics. See [docs/model_evaluation.md](docs/model_evaluation.md).

## Final Model
_TBD_

## Results
_TBD_ — tables and figures go in `results/`.

## Explainable AI
_TBD_ — see [docs/explainability.md](docs/explainability.md).

## Architecture
_TBD_ — see [docs/system_architecture.md](docs/system_architecture.md).

## Local Setup
```bash
git clone https://github.com/raj-kedar/Predicting-Pharmaceutical-Powder-Flow-Using-Machine-Learning.git
cd Predicting-Pharmaceutical-Powder-Flow-Using-Machine-Learning
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env    # never commit .env
```

## Deployment
Target: AWS or Azure. Platform files live in `deployment/aws/` and `deployment/azure/`. No credentials are stored in the repository. See [docs/deployment.md](docs/deployment.md).

## Team Contributions
See [docs/team_contributions.md](docs/team_contributions.md).

## Branch Strategy
| Branch | Purpose |
|---|---|
| `main` | Final, tested, approved version (deployed / submitted). No direct pushes. |
| `dev` | Team integration and testing branch. |
| `member/rajkumar`, `member/member2`, `member/member3`, `member/member4` | Individual work branches. |

Workflow: `member/<name>` → PR → `dev` → PR (after testing) → `main`.

- Use **merge commits** (not squash) so each member's commit history is preserved.
- Member branches are **not deleted** after merging.
- Commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Example PR titles: `feat: laboratory data preprocessing`, `feat: classification models`, `docs: update methodology`

```bash
git checkout member/<name>
git pull origin dev            # stay up to date with integration
git add . && git commit -m "feat: ..."
git push origin member/<name>  # then open a PR into dev
```

## Screenshots / Demo
_TBD_
