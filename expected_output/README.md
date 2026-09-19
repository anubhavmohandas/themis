# Expected output

Frozen outputs of the final methodology on the bundled sample, for comparing a
fresh checkout against. Produced by the commands in `REPRODUCE.md`; the
`themis` CLI prints no timestamps, so a correct run matches these files
byte for byte.

| file | command |
|---|---|
| `audit.txt` | `themis audit` |
| `drift.txt` | `themis drift` |
| `bootstrap_both.txt` | `themis bootstrap --both` |
| `anchors.txt` | `themis anchors` |
| `explain_<address>.txt` | `themis explain <address>` |
| `taxonomy.txt`, `sources.txt` | `themis taxonomy`, `themis sources` |
| `metrics_current_reproduction.json` | `python scripts/generate_result_sets.py --mode frozen --out DIR` → `DIR/metrics.json` (the bundled snapshot as shipped) |
| `metrics_final_corrected_candidate.json` | same, `--mode candidate` (claims the paper-era adapters left `unknown` re-derived through the current taxonomy) |

The two metrics files differ only where the structured-label parser changes a
label; see `REPRODUCE.md` for which is which. `meta.config_hash` is removed
from them because it changes with any edit to `themis/config/`.
