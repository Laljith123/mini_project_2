import { getKnowledgeBase, getKnowledgeBaseStats } from "../../lib/knowledgeBase";

export const metadata = {
  title: "Knowledge Base Browser | College Admission Enquiry Assistant",
};

export default function KnowledgeBasePage() {
  const kb = getKnowledgeBase();
  const stats = getKnowledgeBaseStats();

  return (
    <section className="kb-card">
      <div className="card-header">
        <h2>Validated Knowledge Base</h2>
      </div>

      <p className="hint" style={{ marginBottom: "16px" }}>
        This staff reference view shows the dataset the assistant retrieves
        from after schema validation. Every answer shown to students is grounded
        in these records.
      </p>

      <div className="stats">
        <div className="stat">
          <b>{stats.programs}</b>
          <span>Programs</span>
        </div>
        <div className="stat">
          <b>{stats.fee_components}</b>
          <span>Fee components</span>
        </div>
        <div className="stat">
          <b>{stats.faqs}</b>
          <span>FAQs</span>
        </div>
        <div className="stat">
          <b>{stats.facilities}</b>
          <span>Facilities</span>
        </div>
      </div>

      <div className="validation">
        Data validation report:{" "}
        <span className={stats.validation_errors === 0 ? "ok" : ""}>
          {stats.validation_report}
        </span>
      </div>

      <table className="kb-table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Program</th>
            <th>Duration</th>
            <th>Intake</th>
            <th>First-Year Fees</th>
          </tr>
        </thead>
        <tbody>
          {(kb.programs || []).map((p) => (
            <tr key={p.code}>
              <td>
                <strong>{p.code}</strong>
              </td>
              <td>{p.name}</td>
              <td>{p.duration}</td>
              <td>{p.intake}</td>
              <td>Rs. {p.first_year_fees.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
