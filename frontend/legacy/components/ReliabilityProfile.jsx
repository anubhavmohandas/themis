// STEP 16 - always a multidimensional breakdown, never a single 0-100 score.
// Any dimension the backend could not compute renders its stated reason
// instead of a fabricated number.
export default function ReliabilityProfile({ profile }) {
  return (
    <div className="grid cols-2">
      {Object.entries(profile).map(([dim, block]) => (
        <div className="tile" key={dim}>
          <div className="k" style={{ marginBottom: 10 }}>{dim.replaceAll("_", " ")}</div>
          {!block.available ? (
            <div className="muted" style={{ fontSize: 13 }}>Unavailable: {block.reason}</div>
          ) : (
            <table>
              <tbody>
                {Object.entries(block).filter(([k]) => k !== "available").map(([k, val]) => (
                  <tr key={k}>
                    <td style={{ border: "none", padding: "3px 0", color: "var(--muted)" }}>{k.replaceAll("_", " ")}</td>
                    <td className="num" style={{ border: "none", padding: "3px 0" }}>
                      {typeof val === "object" && val !== null ? JSON.stringify(val) : String(val)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
