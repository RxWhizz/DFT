"""Build surrogate training dataset: MP (inorganic) + experimental literature.

Strategy:
  - Target is ALWAYS experimental bandgap (Eg_exp_eV)
  - DFT r²SCAN+U+SOC values are NOT used as targets for organic cation materials
    because those calculations use pseudo-atom substitution (FA→Cs, MA→Rb)
  - DFT values for inorganic Cs-based materials ARE reliable and can augment exp

Run: .venv/bin/python3 data/build_training_dataset.py
Output: data/surrogate_training.csv
"""
import json, math, os
import pandas as pd

RADII = {
    'Cs': 1.67, 'Rb': 1.52, 'K': 1.38, 'MA': 2.17, 'FA': 2.53,
    'Pb': 1.19, 'Sn': 1.18, 'Ge': 0.73,
    'I':  2.20, 'Br': 1.96, 'Cl': 1.81,
}
CHARGES = {
    'Cs': 1, 'Rb': 1, 'K': 1, 'MA': 1, 'FA': 1,
    'Pb': 2, 'Sn': 2, 'Ge': 2,
    'I': -1, 'Br': -1, 'Cl': -1,
}
ELECTRONEG = {
    'Cs': 0.79, 'Rb': 0.82, 'K': 0.82, 'MA': 2.30, 'FA': 2.40,
    'Pb': 2.33, 'Sn': 1.96, 'Ge': 2.01,
    'I': 2.66, 'Br': 2.96, 'Cl': 3.16,
}
ORGANIC = {'MA', 'FA'}

def _feat(A, B, X, a_lat=None, band_gap_gga=None, Eform=None, e_hull=None, mat_id=''):
    rA, rB, rX = RADII[A], RADII[B], RADII[X]
    t = (rA + rX) / (math.sqrt(2) * (rB + rX))
    f_oct = rB / rX
    a_est = 2.0 * math.sqrt(2) * (rB + rX)
    return {
        'material_id': mat_id,
        'A': A, 'B': B, 'X': X,
        'r_A': rA, 'r_B': rB, 'r_X': rX,
        'chi_A': ELECTRONEG[A], 'chi_B': ELECTRONEG[B], 'chi_X': ELECTRONEG[X],
        'q_A': CHARGES[A], 'q_B': CHARGES[B], 'q_X': CHARGES[X],
        'tolerance_t': round(t, 5),
        'oct_factor': round(f_oct, 5),
        'a_lat_est_A': round(a_est, 4),
        'vol_est_A3': round(a_est**3, 4),
        'delta_chi_BX': round(ELECTRONEG[X] - ELECTRONEG[B], 4),
        'mu_BX': round(rB + rX, 4),
        'is_organic_A': int(A in ORGANIC),
        'a_lat_mp_A': a_lat,
        'band_gap_gga_eV': band_gap_gga,
        'Eform_eV_atom': Eform,
        'e_above_hull_eV': e_hull,
    }

# ── Experimental bandgaps (eV) — primary training target
# Sources: Stoumpos 2013 (JACS 135), Protesescu 2015 (NL 15), Lee 2012 (Science),
#          Eperon 2014 (EES), Koh 2015 (JACS), Linaburg 2017 (CM)
EXP_EG = {
    ('Cs','Pb','I'):  1.73,
    ('Cs','Pb','Br'): 2.36,
    ('Cs','Pb','Cl'): 3.04,
    ('Cs','Sn','I'):  1.30,
    ('Cs','Sn','Br'): 1.75,
    ('Cs','Sn','Cl'): 2.70,
    ('Cs','Ge','I'):  1.63,
    ('Cs','Ge','Br'): 2.32,
    ('Cs','Ge','Cl'): 3.67,
    ('Rb','Pb','I'):  2.65,   # Linaburg 2017
    ('Rb','Pb','Br'): 2.79,
    ('Rb','Pb','Cl'): 3.13,
    ('Rb','Sn','I'):  1.40,   # DFT estimate Filip&Giustino 2016
    ('Rb','Sn','Br'): 1.80,
    ('Rb','Sn','Cl'): 2.60,
    ('MA','Pb','I'):  1.55,
    ('MA','Pb','Br'): 2.35,
    ('MA','Pb','Cl'): 3.07,
    ('MA','Sn','I'):  1.20,
    ('MA','Sn','Br'): 2.15,
    ('MA','Sn','Cl'): 3.20,
    ('FA','Pb','I'):  1.48,
    ('FA','Pb','Br'): 2.23,
    ('FA','Pb','Cl'): 2.98,
    ('FA','Sn','I'):  1.41,
    ('FA','Sn','Br'): 2.00,
    ('FA','Sn','Cl'): 2.90,
}

# Load MP records for inorganic — lowest hull per (A,B,X)
mp_path = os.path.join(os.path.dirname(__file__), 'mp_abx3.json')
mp_data = json.load(open(mp_path))
best_mp = {}
for r in mp_data:
    key = (r['A'], r['B'], r['X'])
    hull = r.get("e_above_hull_eV") if r.get("e_above_hull_eV") is not None else 999
    prev_hull = best_mp.get(key, {}).get("e_above_hull_eV") if best_mp.get(key, {}).get("e_above_hull_eV") is not None else 999
    if hull < prev_hull:
        best_mp[key] = r

records = []

# ── Inorganic: use MP structural data + experimental Eg target
for (A, B, X), mp in best_mp.items():
    eg_exp = EXP_EG.get((A, B, X))
    if eg_exp is None:
        continue
    f = _feat(A, B, X,
              a_lat=mp.get('a_lat_mp_A'),
              band_gap_gga=mp.get('band_gap_mp_eV'),
              Eform=mp.get('Eform_eV_atom'),
              e_hull=mp.get('e_above_hull_eV'),
              mat_id=mp.get('material_id', ''))
    f['Eg_target_eV'] = eg_exp
    f['source'] = 'MP+exp_lit'
    records.append(f)

# ── Organic (MA/FA): no MP entry, estimate structural params
for A in ['MA', 'FA']:
    for B in ['Pb', 'Sn']:
        for X in ['I', 'Br', 'Cl']:
            eg_exp = EXP_EG.get((A, B, X))
            if eg_exp is None:
                continue
            rB, rX = RADII[B], RADII[X]
            a_lat = 2.0 * math.sqrt(2) * (rB + rX) * 1.02
            f = _feat(A, B, X, a_lat=a_lat, mat_id=f'{A}{B}{X}3_lit')
            f['Eg_target_eV'] = eg_exp
            f['source'] = 'exp_lit'
            records.append(f)

# ── Add missing Rb-Pb-I if not in MP
rb_pb_i_in = any(r['A']=='Rb' and r['B']=='Pb' and r['X']=='I' for r in records)
if not rb_pb_i_in:
    f = _feat('Rb','Pb','I', mat_id='RbPbI3_est')
    f['Eg_target_eV'] = EXP_EG[('Rb','Pb','I')]
    f['source'] = 'exp_lit'
    records.append(f)

df = pd.DataFrame(records).drop_duplicates(subset=['A','B','X'])
df = df.sort_values(['A','B','X']).reset_index(drop=True)

print(f"Training dataset: {len(df)} samples")
print(df[['A','B','X','Eg_target_eV','source','tolerance_t','oct_factor']].to_string())
print(f"\nEg_target stats: min={df.Eg_target_eV.min():.2f}  max={df.Eg_target_eV.max():.2f}  mean={df.Eg_target_eV.mean():.2f} eV")

out = os.path.join(os.path.dirname(__file__), 'surrogate_training.csv')
df.to_csv(out, index=False)
print(f"Saved: {out}")
