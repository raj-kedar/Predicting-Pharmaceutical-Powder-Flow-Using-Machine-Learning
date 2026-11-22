/** Browser copy of src/features/flow_metrics.py for the public calculator. Nothing is saved. */
const CLASSES = ['Excellent', 'Good', 'Fair', 'Passable', 'Poor', 'Very poor', 'Very, very poor'];
const CARR_EDGES = [10, 15, 20, 25, 31, 37];
const HAUSNER_EDGES = [1.11, 1.18, 1.25, 1.34, 1.45, 1.59];

const clean = (value: number) => Number(value.toFixed(9));
const band = (value: number, edges: number[]) => {
  const index = edges.findIndex((edge) => value <= edge);
  return CLASSES[index === -1 ? edges.length : index];
};

export type FlowCalc =
  | { ok: true; carr: number; hausner: number; flowClass: string; hausnerClass: string; poor: boolean; acceptable: boolean }
  | { ok: false; message: string };

export function calculateFlow(bulkText: string, tappedText: string): FlowCalc {
  if (!bulkText.trim() || !tappedText.trim()) return { ok: false, message: 'Enter both densities.' };
  const bulk = Number(bulkText);
  const tapped = Number(tappedText);
  if (!Number.isFinite(bulk) || !Number.isFinite(tapped)) return { ok: false, message: 'Densities must be numbers.' };
  if (bulk <= 0 || tapped <= 0) return { ok: false, message: 'Densities must be greater than zero.' };
  if (bulk > 5 || tapped > 5) return { ok: false, message: 'Above 5 g/mL is not plausible. Check the units.' };
  if (tapped < bulk) return { ok: false, message: 'Tapped density cannot be below bulk density.' };
  const carr = clean(((tapped - bulk) / tapped) * 100);
  const hausner = clean(tapped / bulk);
  return {
    ok: true, carr, hausner, flowClass: band(carr, CARR_EDGES), hausnerClass: band(hausner, HAUSNER_EDGES),
    poor: carr >= 25, acceptable: carr <= 20,
  };
}
