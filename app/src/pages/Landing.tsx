import { useState } from 'preact/hooks';
import { api, type SitePerson } from '../api';
import { LAB_POWDERS, UNIVERSITY } from '../content';
import { ProtectedImage, useSiteContent } from '../photos';
import { calculateFlow } from '../flow';
import { PlanCard } from './Billing';
import { Field, Icon, inputValue, percent, Tile, useLoad, UspScale } from '../ui';
import '../landing.css';
import { BrandMark } from '../brand';
import { HowToUse, WhyBuilt } from './Guide';

const SOURCES = {
  usp: 'https://www.usp.org/sites/default/files/usp/document/harmonization/gen-chapter/20230428HSm99885.pdf',
  pat: 'https://www.fda.gov/media/71012/download',
  q8: 'https://database.ich.org/sites/default/files/Q8_R2_Guideline.pdf',
  q13: 'https://www.fda.gov/media/165775/download',
  advanced: 'https://www.fda.gov/emergency-preparedness-and-response/medical-countermeasure-mcm-issues/advanced-manufacturing',
  twin: 'https://www.sciencedirect.com/science/article/abs/pii/S0378517322008912',
  twinReview: 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12516570/',
  blend: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12055667/',
  factory: 'https://www.nature.com/articles/s41467-026-71204-6',
};

const IMPACT = [
  ['Consistent doses', 'Tablet dies and capsules are filled by volume. When powder feeds unevenly, fill weight can drift, and so can the dose in each unit.'],
  ['Uninterrupted production', 'Cohesive powders can bridge over a hopper outlet or form a rat-hole, starving the line and forcing stoppages.'],
  ['Uniform blends', 'How a powder moves affects how evenly the drug stays distributed with excipients through transfer and feeding.'],
  ['Better formulation choices', 'Knowing flow early helps teams choose excipients and processes before scarce drug substance is spent on trials.'],
];

const JOURNEY = [
  ['Dispense', 'Accurate, repeatable material transfer'],
  ['Blend', 'Even mixing of drug and excipients'],
  ['Feed', 'Steady movement through hoppers'],
  ['Compress or fill', 'Uniform die and capsule filling'],
  ['Finished dose', 'Consistent weight and content'],
];

const METHODS = [
  ['Angle of repose', 'The slope of a settled powder cone. Steeper usually means poorer flow.'],
  ['Carr’s index and Hausner ratio', 'Compare bulk and tapped density to show how much a powder consolidates.'],
  ['Flow through an orifice', 'Measures how quickly powder discharges through an opening.'],
  ['Shear cell', 'Measures the force needed to make consolidated powder start moving.'],
];

const SHIFTS = [
  ['Test at the end', 'Build quality into the process'],
  ['Stop-start batches', 'Continuous manufacturing'],
  ['Offline lab checks', 'Timely in-process measurement'],
  ['Trial and error', 'Predictive and digital models'],
];

const TIMELINE = [
  ['2004', 'Process Analytical Technology', 'FDA’s PAT framework promotes understanding and controlling processes through timely measurement.', SOURCES.pat, 'FDA PAT guidance'],
  ['2009', 'Quality by Design', 'ICH Q8(R2) sets out how product and process understanding can support development.', SOURCES.q8, 'ICH Q8(R2)'],
  ['2023', 'Continuous manufacturing', 'FDA issues the final ICH Q13 guidance, giving a harmonized basis for continuous production.', SOURCES.q13, 'ICH Q13'],
  ['Now', 'Digital twins', 'Hybrid models simulate continuous tablet lines to predict blend and tablet properties.', SOURCES.twin, 'Digital twin study'],
  ['Now', 'Machine learning', 'Researchers report up to 87% accuracy classifying blend flow from constituent properties in a 410-blend study.', SOURCES.blend, 'Blend flow study'],
  ['Next', 'Self-driving formulation', 'Automated data factories are being explored to link particle properties, flow and tablet strength.', SOURCES.factory, 'Nature Communications'],
];

const REFERENCES: [string, string][] = [
  ['USP <1174> Powder Flow', SOURCES.usp], ['FDA PAT Guidance (2004)', SOURCES.pat], ['ICH Q8(R2) Pharmaceutical Development', SOURCES.q8],
  ['FDA / ICH Q13 Continuous Manufacturing (2023)', SOURCES.q13], ['FDA Advanced Manufacturing', SOURCES.advanced],
  ['Digital twin of a continuous direct compression line', SOURCES.twin], ['Digital twins from discovery to manufacturing (review)', SOURCES.twinReview],
  ['Predicting powder blend flowability using ML', SOURCES.blend], ['Digital formulator and self-driving tableting data factory', SOURCES.factory],
];

const STUCK = [
  ['Arching (bridging)', 'Particles lock into a stable arch above the hopper outlet, and flow stops completely.'],
  ['Rat-holing', 'Only a narrow channel above the outlet keeps moving, while the rest of the powder stays stagnant.'],
  ['Erratic or flooding flow', 'Powder alternates between stalling and rushing out, so feed rate is unpredictable.'],
  ['Segregation', 'Particles separate by size or density while moving, so drug content drifts between units.'],
];
const CONSEQUENCES = ['Hopper stalls or surges', 'Dies fill unevenly', 'Tablet weight and dose drift',
  'Line stops, batch held for investigation', 'Rework, rejection and delayed supply'];

const NEEDS = [
  ['Tests are slow and scattered', 'Flow tests need equipment, material and time, and results often sit in separate spreadsheets.'],
  ['Data is not always plausible', 'Swapped or mistyped readings can produce impossible results that silently distort decisions.'],
  ['Accuracy claims can mislead', 'Models tested on replicates of the same powders can look far better than they really are.'],
  ['Results need a record', 'Teams need to know who produced a result, how, with which model, and who reviewed it.'],
];

const SOLVED = [
  ['Impossible readings caught', 'Every Aspirin record in the lab data showed tapped density below bulk density, which is physically impossible. It was excluded, and such input is now rejected automatically.', 'Data quality'],
  ['Inflated accuracy exposed', 'A random train/test split raised accuracy from 30.0% to 67.5% only because replicates of the same powder leaked into testing. FlowLytix validates on materials the model has never seen.', 'Honest validation'],
  ['Circular shortcuts removed', 'Using Carr’s index or Hausner ratio as inputs reached 99.8%, but only because the answer is calculated from them. Both are excluded from every model.', 'No leakage'],
  ['Exact answers when possible', 'With bulk and tapped density, FlowLytix calculates the USP class directly, handling band-edge rounding correctly, instead of guessing.', 'Exact first'],
  ['Results that hold up later', 'Results are frozen, attributed, independently reviewed and logged in an append-only audit trail.', 'Traceability'],
];

function Stuck() {
  return (
    <section class="lp-section" id="stuck">
      <div class="lp-wrap">
        <div class="lp-head"><span class="eyebrow">When powder gets stuck</span><h2>One stalled hopper can stop a whole production line</h2>
          <p>Cohesive or poorly flowing powders cause a few well-known failure modes. Each one turns into a quality or supply problem downstream.</p></div>
        <div class="impact-grid">{STUCK.map(([title, text]) => <article class="card problem" key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
        <ol class="chain" aria-label="How a flow problem spreads">{CONSEQUENCES.map((step) => <li key={step}>{step}</li>)}</ol>
      </div>
    </section>
  );
}

function Need() {
  return (
    <section class="lp-section alt" id="need">
      <div class="lp-wrap">
        <div class="lp-head"><span class="eyebrow">Why FlowLytix is needed</span><h2>Flow decisions deserve fast, honest and traceable answers</h2></div>
        <div class="impact-grid">{NEEDS.map(([title, text]) => <article class="card" key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
        <div class="lp-head solved-head"><span class="eyebrow">Problems we solved</span><h2>What building FlowLytix uncovered and fixed</h2></div>
        <div class="solved-grid">
          {SOLVED.map(([title, text, tag]) => <article class="solved" key={title}><span class="chip">{tag}</span><h3>{title}</h3><p>{text}</p></article>)}
        </div>
      </div>
    </section>
  );
}

function LabStudy() {
  const valid = LAB_POWDERS.filter((powder) => !powder.excluded).length;
  return (
    <section class="lp-section" id="lab">
      <div class="lp-wrap">
        <div class="lp-head"><span class="eyebrow">Our lab study</span><h2>Grounded in real measurements at {UNIVERSITY}</h2>
          <p>This project began in the laboratory. Pharmaceutical powders available in the labs at {UNIVERSITY} were measured by the project team, each one repeated fifteen times.</p></div>
        <div class="stat-grid lab-stats">
          <Tile label="Powders measured" value="18" />
          <Tile label="Replicates each" value="15" />
          <Tile label="Lab measurements" value="270" />
          <Tile label="Valid powders" value={valid} />
        </div>
        <p class="lab-measured">Measured for every replicate: sample weight, bulk density, tapped density and angle of repose, with Carr’s index, Hausner ratio and USP flow character calculated from them.</p>
        <ul class="powder-grid" aria-label="Powders measured in the lab">
          {LAB_POWDERS.map((powder) => (
            <li key={powder.name} class={powder.excluded ? 'is-excluded' : ''}>
              <span>{powder.name}</span>
              <span class={`badge ${powder.excluded ? 'badge-poor' : FLOW_TONE[powder.flow] ?? 'badge-mid'}`}>{powder.flow}</span>
            </li>
          ))}
        </ul>
        <p class="lp-note">Classes show the most common USP flow character across each powder’s replicates. Aspirin was excluded because its readings were physically impossible. Eighteen powders are too few to train and fairly test a model, so the screening models in this app are trained on a separate compiled dataset of 70 materials. The lab data was used to study flow behaviour and to expose the validation problems described above.</p>
      </div>
    </section>
  );
}

const FLOW_TONE: Record<string, string> = {
  Excellent: 'badge-good', Good: 'badge-good', Fair: 'badge-good', Passable: 'badge-mid',
  Poor: 'badge-poor', 'Very poor': 'badge-poor', 'Very, very poor': 'badge-poor',
};

function Pricing({ signedIn }: { signedIn: boolean }) {
  const { data, error } = useLoad(() => api.plans(), []);
  const target = signedIn ? '#/billing' : '#/register';
  return (
    <section class="lp-section alt" id="pricing">
      <div class="lp-wrap">
        <div class="lp-head"><span class="eyebrow">Plans</span><h2>Start free. Upgrade when you need estimates.</h2>
          <p>Exact USP classification is always available on the Free plan. Each paid plan runs for 30 days and does not renew automatically.</p></div>
        {error && <p class="muted">Plans could not be loaded right now.</p>}
        {data && <div class="plan-grid">
          {data.plans.map((plan) => <PlanCard key={plan.code} plan={plan} action={
            <a class={plan.code === 'pro' ? 'btn btn-primary btn-block' : 'btn btn-ghost btn-block'} href={target}>
              {plan.code === 'free' ? 'Start free' : `Choose ${plan.name}`}</a>} />)}
        </div>}
        <p class="fineprint">Secure payments by Razorpay. See <a href="#/terms">Terms</a> and <a href="#/refunds">Refund &amp; cancellation policy</a>.</p>
      </div>
    </section>
  );
}

function PersonCard({ person }: { person: SitePerson }) {
  return (
    <article class="team-card">
      {person.photo_url
        ? <ProtectedImage class="photo-frame has-photo" src={person.photo_url} alt={`Photo of ${person.name}`} />
        : <div class="photo-frame" role="img" aria-label={`Photo placeholder for ${person.name}`} />}
      <h3>{person.name}</h3>
      <p>{person.role}</p>
    </article>
  );
}

function Team() {
  const { team, guides } = useSiteContent();
  return (
    <section class="lp-section" id="team">
      <div class="lp-wrap">
        <div class="lp-head"><span class="eyebrow">The team</span><h2>The people behind FlowLytix</h2>
          <p>Built by the FlowLytix team, with laboratory work at {UNIVERSITY}.</p></div>
        <div class="team-grid">{team.map((person, index) => <PersonCard key={`t${index}`} person={person} />)}</div>
        {guides.length > 0 && <>
          <h3 class="guides-title">Project guides</h3>
          <div class="team-grid guides">{guides.map((person, index) => <PersonCard key={`g${index}`} person={person} />)}</div>
        </>}
      </div>
    </section>
  );
}

function Hoppers() {
  const falling = [0, 1, 2, 3, 4, 5];
  const packed: [number, number][] = [];
  for (let row = 0; row < 5; row++) {
    const count = 8 - row;
    for (let col = 0; col < count; col++) packed.push([20 + row * 7 + col * 14, 42 + row * 13]);
  }
  const hopper = 'M8 20H132V92L82 142V164H58V142L8 92Z';
  return (
    <svg class="hoppers" viewBox="0 0 340 250" role="img"
      aria-label="Two hoppers. Free-flowing powder falls steadily; cohesive powder forms an arch and stops.">
      <g transform="translate(14 8)">
        <path d={hopper} class="hopper" />
        {packed.map(([x, y]) => <circle key={`a${x}-${y}`} cx={x} cy={y} r="5.5" class="grain" />)}
        <circle cx="62" cy="112" r="5" class="grain" /><circle cx="78" cy="112" r="5" class="grain" />
        <circle cx="70" cy="126" r="5" class="grain" />
        {falling.map((item) => (
          <circle key={item} cx={63 + (item % 3) * 7} cy="148" r="3.6" class="grain falling" style={{ animationDelay: `${item * 0.22}s` }} />
        ))}
        <text x="70" y="226" class="hopper-label">Free flowing</text>
      </g>
      <g transform="translate(186 8)">
        <path d={hopper} class="hopper" />
        {packed.map(([x, y]) => <circle key={`b${x}-${y}`} cx={x} cy={y} r="5.5" class="grain" />)}
        <path d="M34 112Q70 80 106 112" class="arch" />
        <text x="70" y="226" class="hopper-label">Arching</text>
      </g>
    </svg>
  );
}

function Calculator() {
  const [bulk, setBulk] = useState('0.45');
  const [tapped, setTapped] = useState('0.58');
  const result = calculateFlow(bulk, tapped);
  return (
    <div class="calc card">
      <div class="calc-inputs">
        <h3>Try the USP calculation</h3>
        <p class="muted">Enter two lab readings. It runs in your browser and nothing is saved.</p>
        <div class="form-grid">
          <Field label="Bulk density" unit="g/mL"><input inputMode="decimal" value={bulk} onInput={(event) => setBulk(inputValue(event))} /></Field>
          <Field label="Tapped density" unit="g/mL"><input inputMode="decimal" value={tapped} onInput={(event) => setTapped(inputValue(event))} /></Field>
        </div>
      </div>
      <div class="calc-result" aria-live="polite">
        {result.ok ? <>
          <span class="muted">Flow character</span>
          <strong class="calc-class">{result.flowClass}</strong>
          <div class="tiles">
            <Tile label="Carr’s index" value={`${result.carr.toFixed(2)}%`} />
            <Tile label="Hausner ratio" value={result.hausner.toFixed(3)} />
          </div>
          <UspScale active={result.flowClass} />
          {result.hausnerClass !== result.flowClass && (
            <p class="muted small">Hausner ratio gives “{result.hausnerClass}”. The two scales can differ near a band edge.</p>
          )}
        </> : <p class="calc-error" role="alert">{result.message}</p>}
      </div>
    </div>
  );
}

export function Landing({ signedIn, theme, onTheme }: { signedIn: boolean; theme: string; onTheme: () => void }) {
  const { data: card } = useLoad(() => api.modelCard(), []);
  const tiers = card ? ['full', 'mid', 'basic'].map((name) => card.ml_tiers[name]).filter(Boolean) : [];
  const appLink = signedIn ? '#/' : '#/login';
  const appLabel = signedIn ? 'Open dashboard' : 'Sign in';
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

  return (
    <div class="landing">
      <header class="lp-nav">
        <a class="lp-brand" href="#/welcome" onClick={(event) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
          <BrandMark />
          FlowLytix
        </a>
        <nav aria-label="Page sections">
          <button type="button" onClick={() => scrollTo('purpose')}>Why FlowLytix</button>
          <button type="button" onClick={() => scrollTo('guide')}>How to use</button>
          <button type="button" onClick={() => scrollTo('lab')}>Lab study</button>
          <button type="button" onClick={() => scrollTo('pricing')}>Pricing</button>
          <button type="button" onClick={() => scrollTo('team')}>Team</button>
        </nav>
        <div class="lp-nav-right">
          <button class="icon-btn" type="button" onClick={onTheme} aria-label={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>
          {!signedIn && <a class="btn btn-ghost nav-signup" href="#/register">Start free</a>}
          <a class="btn btn-outline" href={appLink}>{appLabel}</a>
        </div>
      </header>

      <main>
        <section class="lp-hero">
          <div class="lp-wrap hero-grid">
            <div>
              <span class="eyebrow">Pharmaceutical powder flowability</span>
              <h1>Every reliable tablet starts with powder that flows.</h1>
              <p>Flowability shapes dose consistency, line stability and development speed. As medicine manufacturing moves toward continuous, data-driven production, understanding it early matters more than ever.</p>
              <div class="hero-actions">
                <button class="btn btn-light" type="button" onClick={() => scrollTo('measure')}>Try the calculator</button>
                <a class="btn btn-clear" href={signedIn ? appLink : '#/register'}>{signedIn ? appLabel : 'Start free'}</a>
              </div>
            </div>
            <Hoppers />
          </div>
        </section>

        <Stuck />
        <WhyBuilt />

        <section class="lp-section alt" id="why">
          <div class="lp-wrap">
            <div class="lp-head"><span class="eyebrow">Why it matters</span><h2>A small powder property with a large manufacturing impact</h2>
              <p>Most solid doses begin as powder. Before a tablet or capsule exists, that powder must move predictably through every step.</p></div>
            <div class="impact-grid">
              {IMPACT.map(([title, text], index) => <article class="card" key={title}><span class="num-mark">0{index + 1}</span><h3>{title}</h3><p>{text}</p></article>)}
            </div>
            <ol class="journey" aria-label="Where flow matters in production">
              {JOURNEY.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}
            </ol>
          </div>
        </section>

        <section class="lp-section" id="measure">
          <div class="lp-wrap">
            <div class="lp-head"><span class="eyebrow">How it is measured</span><h2>Four established tests, one shared language</h2>
              <p>USP &lt;1174&gt; describes four common approaches. No single test captures everything, and results depend on the method used, so conditions should always be reported.</p></div>
            <div class="method-grid">{METHODS.map(([title, text]) => <article key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
            <Calculator />
          </div>
        </section>

        <section class="lp-section alt" id="transform">
          <div class="lp-wrap">
            <div class="lp-head"><span class="eyebrow">Industry transformation</span><h2>From testing quality to designing it in</h2>
              <p>FDA’s PAT guidance captures the shift in one line: “quality cannot be tested into products.” Flow is now something to understand, predict and control.</p></div>
            <div class="shift-grid">
              {SHIFTS.map(([from, to]) => <div class="shift" key={to}><span>{from}</span><b aria-hidden="true">→</b><strong>{to}</strong></div>)}
            </div>
            <ol class="timeline">
              {TIMELINE.map(([year, title, text, url, label]) => (
                <li key={title}><span class="year">{year}</span><div><h3>{title}</h3><p>{text}</p>
                  <a href={url} target="_blank" rel="noopener noreferrer">{label}</a></div></li>
              ))}
            </ol>
            <p class="lp-note">FDA describes continuous manufacturing as having the potential to improve the efficiency, flexibility, agility and robustness of production. Consistent material flow is central to running it well.</p>
          </div>
        </section>

        <Need />

        <section class="lp-section" id="platform">
          <div class="lp-wrap">
            <div class="lp-head"><span class="eyebrow">The FlowLytix platform</span><h2>The right method for the measurements you have</h2>
              <p>When an exact answer is possible, FlowLytix calculates it. When it is not, the result is clearly labelled as an estimate.</p></div>
            <div class="path-grid">
              <article class="card card-accent"><span class="badge badge-exact">Exact · USP</span><h3>Bulk + tapped density</h3>
                <p>Calculates Carr’s index and Hausner ratio, then applies the USP &lt;1174&gt; scale. No model is involved.</p></article>
              <article class="card card-accent"><span class="badge badge-ml">ML estimate</span><h3>Tapped density not measured</h3>
                <p>Screens for poor flow from the measurements available, always tested on materials the model had not seen.</p></article>
            </div>
            {tiers.length > 0 && (
              <div class="tier-strip" aria-label="Validated model accuracy">
                {tiers.map((tier) => (
                  <div key={tier.tier}><strong>{percent(tier.lomo_accuracy)}</strong><span class="tier-title">{tier.tier} tier</span>
                    <small>{tier.features.length} measurements</small></div>
                ))}
                <div><strong>{tiers[0].n_materials}</strong><span class="tier-title">unseen materials</span><small>leave-one-material-out</small></div>
              </div>
            )}
            <div class="feature-row">
              <span>Role-based access</span><span>Independent review</span><span>Append-only audit trail</span><span>Frozen, attributable results</span>
            </div>
            <aside class="honest">
              <h3>What these numbers do and do not mean</h3>
              <ul>
                <li>The 92% tier requires a measured flow rate, which is itself a flow measurement.</li>
                <li>Models were trained on a compiled dataset and have not been validated on an independent experimental campaign.</li>
                <li>Blend prediction is not available yet. Current models cover individual powders.</li>
                <li>FlowLytix supports screening and development decisions. It is not a GMP-validated system, so do not use it alone for QC, batch release or regulatory decisions.</li>
              </ul>
            </aside>
          </div>
        </section>

        <HowToUse />
        <LabStudy />
        <Pricing signedIn={signedIn} />
        <Team />

        <section class="lp-cta">
          <div class="lp-wrap"><h2>Turn your lab readings into a clear flow result.</h2>
            <a class="btn btn-light" href={signedIn ? appLink : '#/register'}>{signedIn ? 'Open dashboard' : 'Create a free account'}</a></div>
        </section>
      </main>

      <footer class="lp-footer">
        <div class="lp-wrap">
          <h2>Sources</h2>
          <ul>{REFERENCES.map(([label, url]) => <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{label}</a></li>)}</ul>
          <nav class="legal-links" aria-label="Policies">
            <a href="#/terms">Terms</a><a href="#/privacy">Privacy</a><a href="#/refunds">Refunds &amp; cancellation</a><a href="#/contact">Contact</a>
          </nav>
          <p>General information, not regulatory, medical or manufacturing advice. FlowLytix is not affiliated with or endorsed by USP, FDA, ICH or Razorpay.</p>
        </div>
      </footer>
    </div>
  );
}
