export default function Legend() {
  return (
    <div className="legend" aria-label="Graph legend">
      <span><i className="lg lg-pill" /> Entry / Exit</span>
      <span><i className="lg lg-block" /> Basic block</span>
      <span><i className="lg lg-diamond" /> Decision</span>
      <span><i className="lg lg-switch" /> Switch</span>
      <span><i className="lg lg-dead" /> Unreachable</span>
      <span><i className="lg lg-back" /> Loop back edge</span>
    </div>
  );
}
