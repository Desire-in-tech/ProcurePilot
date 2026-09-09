import { ArrowRight, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

function Overview() {
  return (
    <div className="page">
      <header className="hero">
        <div className="hero-content">
          <p className="eyebrow">AI-ASSISTED PROCUREMENT</p>
          <h1>
            From “We need this”
            <br />
            to “Here’s the best supplier.”
          </h1>
          <p className="hero-description">
            ProcurePilot helps you define requirements, discover suppliers,
            compare options and move toward a purchasing decision.
          </p>

          <Link to="/procurements" className="primary-button hero-button">
            Start a procurement
            <ArrowRight size={18} />
          </Link>
        </div>

        <div className="hero-agent">
          <div className="agent-symbol">
            <Sparkles size={28} />
          </div>
          <span>ProcurePilot Agent</span>
          <strong>Ready to help you source.</strong>
        </div>
      </header>

      <section className="workflow-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">HOW IT WORKS</p>
            <h2>A procurement workflow built around decisions.</h2>
          </div>
        </div>

        <div className="workflow-grid">
          <div className="workflow-card">
            <span>01</span>
            <Search size={22} />
            <h3>Define</h3>
            <p>
              Describe what you need. ProcurePilot turns your request into
              structured procurement requirements.
            </p>
          </div>

          <div className="workflow-card">
            <span>02</span>
            <Search size={22} />
            <h3>Discover</h3>
            <p>
              Find relevant suppliers and products based on the requirements
              that matter to you.
            </p>
          </div>

          <div className="workflow-card">
            <span>03</span>
            <ShieldCheck size={22} />
            <h3>Compare</h3>
            <p>
              Evaluate supplier options using the requirements, pricing and
              evidence available.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

export default Overview
