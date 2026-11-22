import { BrandWordmark } from '../brand';
import { PageHead } from '../ui';

const REASONS = [
  ['Flow problems are found too late', 'A powder that flows badly is often discovered only when it jams a hopper or gives uneven tablets. By then, time and expensive drug substance are already spent.'],
  ['The full test is not always available', 'The exact flow class needs tapped density, which takes equipment and time. Many labs have only a few quick measurements at first.'],
  ['People need an early, honest answer', 'Teams want to know early whether a powder is likely to flow poorly, so they can change the formula or process before scale-up.'],
];

const GIVES = [
  ['An exact answer when you have the data', 'With bulk and tapped density, FlowLytix calculates the official USP flow class directly. No guessing.'],
  ['A clear early warning when you do not', 'With simpler measurements, the model estimates whether the powder is likely to flow poorly, and tells you how reliable that estimate is.'],
  ['A record you can trust later', 'Every result is saved with who made it, how, and who checked it, so decisions can be explained months later.'],
];

const STEPS = [
  ['Create your account', 'Click "Start free" and sign up with your email. The Free plan is enough to try exact USP results.'],
  ['Measure your powder', 'For an exact result, measure bulk density and tapped density in g/mL. If you cannot measure tapped density, measure angle of repose, and if possible particle size, moisture and flow rate.'],
  ['Open "Classify powder"', 'Type your numbers into the boxes. The coloured strip at the top tells you which kind of answer you will get before you click.'],
  ['Click "Classify" and read the result', 'The big word is the flow class, from Excellent to Very, very poor. The badge says "Exact · USP" for a calculated answer or "ML estimate" for a model estimate.'],
  ['Save it as a sample (recommended)', 'Use "Samples" to record the material, batch and replicate, then classify it from there. This keeps a clean history for each batch.'],
  ['Get it reviewed', 'A reviewer opens the result under "Results & review" and approves it. Nobody can approve their own result.'],
];

const READING = [
  ['Excellent, Good, Fair', 'The powder should flow well enough for normal tableting or capsule filling.'],
  ['Passable', 'Borderline. It may work, but watch for uneven fill weights.'],
  ['Poor or worse', 'Expect flow problems. Discuss options such as a flow aid (glidant) or granulation with your formulation team.'],
  ['ML estimate', 'A screening guide, not a measurement. Measure tapped density to confirm before making a decision.'],
];

const TIPS = [
  'Use g/mL for densities. Tapped density can never be lower than bulk density; if it is, the readings were swapped.',
  'More measurements give a better estimate. Flow rate is the single most useful extra measurement.',
  'If a reading was entered wrongly, void the sample with a reason. Records are never deleted, so the history stays honest.',
  'Free accounts get exact results. Pro and Lab plans add ML estimates and higher monthly limits.',
];

export function WhyBuilt() {
  return (
    <section class="lp-section why-built" id="purpose">
      <div class="lp-wrap why-grid">
        <div>
          <span class="eyebrow">Why we built this model</span>
          <h2>To catch poor powder flow early, before it costs time and material</h2>
          <div class="reason-list">
            {REASONS.map(([title, text]) => <div key={title}><h3>{title}</h3><p>{text}</p></div>)}
          </div>
        </div>
        <div class="why-side">
          <BrandWordmark />
          <h3>What FlowLytix gives you</h3>
          <ul class="gives">{GIVES.map(([title, text]) => <li key={title}><strong>{title}.</strong> {text}</li>)}</ul>
        </div>
      </div>
    </section>
  );
}

export function HowToUse({ inApp = false }: { inApp?: boolean }) {
  return (
    <section class={inApp ? 'guide in-app' : 'lp-section alt guide'} id="guide">
      <div class={inApp ? '' : 'lp-wrap'}>
        {!inApp && <div class="lp-head"><span class="eyebrow">How to use FlowLytix</span><h2>From lab readings to a flow result in six steps</h2>
          <p>No machine-learning knowledge needed. If you can measure a powder, you can use FlowLytix.</p></div>}
        <ol class="steps">
          {STEPS.map(([title, text], index) => (
            <li key={title}><span class="step-num">{index + 1}</span><div><h3>{title}</h3><p>{text}</p></div></li>
          ))}
        </ol>
        <div class="guide-grid">
          <div class="card">
            <h3>How to read your result</h3>
            <dl class="facts">{READING.map(([term, meaning]) => <div key={term}><dt>{term}</dt><dd>{meaning}</dd></div>)}</dl>
          </div>
          <div class="card">
            <h3>Tips for better results</h3>
            <ul class="tips">{TIPS.map((tip) => <li key={tip}>{tip}</li>)}</ul>
          </div>
        </div>
      </div>
    </section>
  );
}

export function HelpPage() {
  return (
    <>
      <PageHead title="How to use FlowLytix" subtitle="A plain-language guide to getting and reading a flow result.">
        <a class="btn btn-primary" href="#/classify">Classify a powder</a>
      </PageHead>
      <HowToUse inApp />
    </>
  );
}
