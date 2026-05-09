# OghmaNano Debug Report

## Sanity check
- total_stack_thickness_nm: 1050.0
- absorber_start_nm: 250.0
- absorber_end_nm: 750.0
- simulated_generation_depth_max_nm: 1047.375
- generation_peak_depth_nm: 254.62500000000003
- generation_warning: none
- Jsc_from_curve_mA_cm2: -24.9434416802048
- Jsc_reported_mA_cm2: -24.943444659798864
- Voc_V: 0.9187499
- FF: 0.7133273
- PCE_reported_pct: 16.34717
- PCE_recomputed_pct: 16.34717
- relative_error_pct: 0.0

## Optical spectrum
- Energy range: 1.05 to 6 eV
- Wavelength range: 206.64 to 1180.8 nm
- alpha range: 0 to 736851 cm^-1
- n range: 0.910024 to 3.24785
- k range: 0 to 2.24235
- Eg marker: 1.5858 eV
- Warnings: Expected DFT optical .npy files are missing; deriving n/k/alpha from dielectric_function.csv.

## Time dependent outputs
- Files found: 825
- Variables detected: Ec, Efield_y, Eg, Ev, Fi, Fn, Fp, G_n, G_p, H_joule_device, Jn, Jn_all, Jn_diffusion, Jn_drift, Jn_drift_plus_diffusion, Jn_plus_Jp, Jn_x, Jn_x_diffusion, Jn_x_drift, Jn_z, Jn_z_diffusion, Jn_z_drift, Jp, Jp_all, Jp_diffusion, Jp_drift, Jp_drift_plus_diffusion, Jp_x, Jp_x_diffusion, Jp_x_drift, Jp_z, Jp_z_diffusion, Jp_z_drift, Nad, Nion, Q_nfree, Q_nfree_and_ntrap, Q_ntrap, Q_pfree, Q_pfree_and_ptrap
- Units inferred: A m^{-2}, K, S/m, V, W m^{-3}, au, eV, m^{-3}, m^{-3} s^{-1}, m^{2} V^{-1} s^{-1}
- Warnings: Snapshot files exist but all recorded times are identical; this is JV snapshot output, not a time transient.

## Files reviewed
- generador fv\calculations\alpha\14_oghma_device_onset_check\sim\sim_info.dat
- generador fv\calculations\alpha\14_oghma_device_onset_check\sim\jv.csv
- generador fv\calculations\alpha\14_oghma_device_onset_check\sim\optical_output\G_y.csv
- generador fv\calculations\alpha\14_oghma_device_onset_check\sim\materials\CsPbI3
- generador fv\calculations\alpha\14_oghma_device_onset_check\device_stack.json

## Recommendations
- Treat Oghma JV current columns and sim_info jsc as A/m^2 unless proven otherwise.
- Recreate the missing DFT optical .npy files or point device_stack.json to the actual optical source.
- Regenerate the Oghma material CSV after the bounded fallback fix, or rerun with true DFT n/k.
