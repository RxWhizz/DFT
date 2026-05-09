# OghmaNano Debug Report

## Sanity check
- total_stack_thickness_nm: 1050.0
- absorber_start_nm: 250.0
- absorber_end_nm: 750.0
- simulated_generation_depth_max_nm: 1048.25
- generation_peak_depth_nm: 250.25
- generation_warning: none
- Jsc_from_curve_mA_cm2: -21.99427001352543
- Jsc_reported_mA_cm2: -21.994276461887903
- Voc_V: 0.8953726
- FF: 0.7061798
- PCE_reported_pct: 13.90685
- PCE_recomputed_pct: 13.90685
- relative_error_pct: 0.0

## Optical spectrum
- Energy range: 1.05 to 6 eV
- Wavelength range: 206.64 to 1180.8 nm
- alpha range: 7.21821e-05 to 735722 cm^-1
- n range: 0.933322 to 3.2127
- k range: 6.7826e-10 to 2.21344
- Eg marker: 1.5858 eV
- Warnings: none

## Time dependent outputs
- Files found: 8625
- Variables detected: Ec, Efield_y, Eg, Ev, Fi, Fn, Fp, G_n, G_p, H_joule_device, Jn, Jn_all, Jn_diffusion, Jn_drift, Jn_drift_plus_diffusion, Jn_plus_Jp, Jn_x, Jn_x_diffusion, Jn_x_drift, Jn_z, Jn_z_diffusion, Jn_z_drift, Jp, Jp_all, Jp_diffusion, Jp_drift, Jp_drift_plus_diffusion, Jp_x, Jp_x_diffusion, Jp_x_drift, Jp_z, Jp_z_diffusion, Jp_z_drift, Nad, Nion, Q_nfree, Q_nfree_and_ntrap, Q_ntrap, Q_pfree, Q_pfree_and_ptrap
- Units inferred: A m^{-2}, K, S/m, V, W m^{-3}, au, eV, m^{-3}, m^{-3} s^{-1}, m^{2} V^{-1} s^{-1}
- Warnings: Snapshot files exist but all recorded times are identical; this is JV snapshot output, not a time transient.

## Files reviewed
- generador fv\calculations\alpha\14_oghma_device\sim\sim_info.dat
- generador fv\calculations\alpha\14_oghma_device\sim\jv.csv
- generador fv\calculations\alpha\14_oghma_device\sim\optical_output\G_y.csv
- generador fv\calculations\alpha\14_oghma_device\sim\materials\CsPbI3
- generador fv\calculations\alpha\14_oghma_device\device_stack.json

## Recommendations
- Treat Oghma JV current columns and sim_info jsc as A/m^2 unless proven otherwise.
- If optical warnings mention missing .npy files, regenerate them from the RPA dielectric CSV before rerunning Oghma.
- If material CSV files are older than the optical .npy files, rerun Oghma preparation so CsPbI3/n.csv and alpha.csv are refreshed.
