# PDF uncertainty on the fiducial W+ cross section

Observable: fiducial cross section for p p -> W+ -> mu+ nu at 13 TeV, NLO QCD,
from our interpolation grid. One convolution per PDF member, each with that
member's own alpha_s; scales, cuts and everything else are the same in every
row.

## Files

Columns: member (the LHAPDF member number), sigma_pb.

- ct18nlo_members.csv: CT18NLO. Member 0 is the central fit; members 1 to 58
  are the 29 eigenvector pairs in LHAPDF order (2k-1 and 2k are the two
  directions of eigenvector k).
- nnpdf31_members.csv: NNPDF31_nlo_as_0118. Member 0 is the average of the
  replicas; members 1 to 100 are the replicas.

## From the sets' .info files

CT18NLO.info

    NumMembers: 59
    ErrorType: hessian
    ErrorConfLevel: 90

NNPDF31_nlo_as_0118.info

    NumMembers: 101
    ErrorType: replicas
