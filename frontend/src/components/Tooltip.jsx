// Every metric that needs one gets a hover/focus explanation, per the spec's
// "every metric should have a tooltip explaining what it means".
export default function Tooltip({ text, children }) {
  return (
    <span className="tip" tabIndex={0}>
      {children}
      <span className="bubble">{text}</span>
    </span>
  );
}
