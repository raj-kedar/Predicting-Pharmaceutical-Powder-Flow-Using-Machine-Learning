/**
 * Fallback site content, shown only if the server's content cannot be loaded.
 * The live team, guides, photos and business details are edited by a superadmin
 * in the admin panel (Admin > Site content).
 */
export const TEAM = [
  { name: 'Team member 1', role: 'Role' },
  { name: 'Team member 2', role: 'Role' },
  { name: 'Team member 3', role: 'Role' },
  { name: 'Team member 4', role: 'Role' },
];
export const GUIDES = [
  { name: 'Project guide 1', role: 'Faculty guide' },
  { name: 'Project guide 2', role: 'Faculty guide' },
];

export const UNIVERSITY = 'MIT Vishwaprayag University';

/** Required on the legal and contact pages before Razorpay live activation. */
export const BUSINESS = {
  name: '[Registered business or owner name]',
  email: '[support email]',
  phone: '[support phone]',
  address: '[registered address]',
  lastUpdated: '[date]',
};

/**
 * Original lab measurements: 18 powders x 15 replicates, flow character by USP <1174>
 * (most common class across the 15 replicates).
 */
export const LAB_POWDERS: { name: string; flow: string; excluded?: boolean }[] = [
  { name: 'Acacia', flow: 'Good' },
  { name: 'Acetyl salicylic acid', flow: 'Fair' },
  { name: 'Ammonium bicarbonate', flow: 'Good' },
  { name: 'Aspirin', flow: 'Excluded', excluded: true },
  { name: 'Bentonite powder', flow: 'Fair' },
  { name: 'Calcium carbonate', flow: 'Good' },
  { name: 'Calcium gluconate', flow: 'Fair' },
  { name: 'Diclofenac sodium', flow: 'Passable' },
  { name: 'L-Arginine', flow: 'Very, very poor' },
  { name: 'Magnesium sulphate', flow: 'Fair' },
  { name: 'Metformin hydrochloride', flow: 'Excellent' },
  { name: 'Paracetamol', flow: 'Poor' },
  { name: 'Sitagliptin', flow: 'Very, very poor' },
  { name: 'Sodium benzoate', flow: 'Good' },
  { name: 'Sodium lauryl sulphate', flow: 'Fair' },
  { name: 'Sodium phosphate', flow: 'Good' },
  { name: 'Talcum powder', flow: 'Fair' },
  { name: 'Tannic acid', flow: 'Good' },
];
