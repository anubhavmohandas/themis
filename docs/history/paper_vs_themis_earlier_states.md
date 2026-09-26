# Paper vs THEMIS: earlier development states

**This page documents earlier development states. It is not the current paper-vs-THEMIS
status.** For the current status see `REPRODUCE.md` and the `themis verify-paper` output.

While THEMIS was being built, an earlier manuscript draft and the paper's own pipeline
differed from THEMIS on 32 numbers. They were reconciled before the final manuscript
(agreement analysis over 15,413 multi-dataset addresses, 10,515 exact agreements,
corrected revenue values). The classes of difference were:

- the §5.1 agreement breakdown: the paper pipeline counted an address `exact` when only
  one interpretable label existed (13,673); THEMIS requires two (10,515) and reports the
  rest `incomparable`;
- WatchYourBack-dependent overlaps and kappa values, after its 87 `#`-prefixed addresses
  were joined;
- the §5.4 exact-rate interval.

The reconciliation record is in `RECONCILIATION_REPORT.md` and `REPRODUCE.md` (sections 4
and 8).
