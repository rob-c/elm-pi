---
skill: qcd-parton-distributions
also: uncertainty-propagation, statistics-and-significance
category: particle-theory
pitfall: the 90% CL eigenvector uncertainty of a CT set quoted as 68% (no division by 1.645); a replica formula used on a Hessian set, or members paired wrongly in the asymmetric formula
timeout_sec: 900
---
ct18nlo_members.csv and nnpdf31_members.csv hold our fiducial W+ cross section computed with every member of CT18NLO and of NNPDF31_nlo_as_0118; notes.md says how they were made and quotes the sets' .info files. I need the PDF uncertainty from each set at 68% CL: for CT18 the symmetric one and the asymmetric up and down ones, for NNPDF the central value and its uncertainty. Write result.json with ct18_sym_pb, ct18_up_pb, ct18_down_pb (all three positive), nnpdf_central_pb and nnpdf_unc_pb.
