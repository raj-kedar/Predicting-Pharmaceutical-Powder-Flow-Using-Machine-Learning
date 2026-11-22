import { api } from '../api';
import { Notice, PageHead, percent, Tile, useLoad } from '../ui';

const FEATURE_LABELS: Record<string, string> = {
  Bulk_Density_g_mL: 'Bulk density', Angle_of_Repose_deg: 'Angle of repose', Mean_Particle_Size_um: 'Particle size',
  Moisture_Content_percent: 'Moisture', Flow_Rate_g_s: 'Flow rate',
};

export function Models() {
  const { data, error, loading } = useLoad(() => api.modelCard(), []);
  const tiers = data ? ['full', 'mid', 'basic'].map((name) => data.ml_tiers[name]).filter(Boolean) : [];
  const sample = tiers[0];

  return (
    <>
      <PageHead title="Model performance" subtitle="How each method was validated, and which measurements it needs." />
      <Notice>{error}</Notice>
      {loading && <p class="muted">Loading…</p>}
      {data && <>
        <section class="card card-accent">
          <h2>Exact path</h2>
          <p>{data.exact_path.method}, used when {data.exact_path.when.toLowerCase()}. This is {data.exact_path.accuracy}.</p>
        </section>
        {sample && <div class="stat-grid three">
          <Tile label="Materials tested unseen" value={sample.n_materials} />
          <Tile label="Measurements" value={sample.n_rows ?? '—'} />
          <Tile label="Majority baseline" value={percent(sample.majority_baseline)} />
        </div>}
        <div class="tier-grid">
          {tiers.map((tier) => (
            <section class="card" key={tier.tier}>
              <span class="tier-name">{tier.tier} tier</span>
              <strong class="tier-accuracy">{percent(tier.lomo_accuracy)}</strong>
              <span class="muted small">leave-one-material-out accuracy</span>
              <div class="meter" role="img" aria-label={`Accuracy ${percent(tier.lomo_accuracy)}, baseline ${percent(tier.majority_baseline)}`}>
                <span class="meter-fill" style={{ width: `${tier.lomo_accuracy * 100}%` }} />
                <span class="meter-mark" style={{ left: `${tier.majority_baseline * 100}%` }} />
              </div>
              <dl class="facts compact">
                <div><dt>Balanced accuracy</dt><dd>{percent(tier.lomo_balanced_acc)}</dd></div>
                <div><dt>Poor-flow detection</dt><dd>{percent(tier.lomo_sensitivity)}</dd></div>
                <div><dt>Acceptable detection</dt><dd>{percent(tier.lomo_specificity)}</dd></div>
              </dl>
              <div class="chips">{tier.features.map((feature) => <span class="chip" key={feature}>{FEATURE_LABELS[feature] ?? feature}</span>)}</div>
            </section>
          ))}
        </div>
        <Notice kind="info">
          The 92% figure applies only when flow rate is measured. The models were trained on a compiled dataset and have not yet been validated on an independent experimental campaign. Use the estimates for screening, and confirm QC or regulatory decisions with validated methods.
        </Notice>
      </>}
    </>
  );
}
