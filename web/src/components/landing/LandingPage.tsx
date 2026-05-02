"use client";

import Link from "next/link";
import { useEffect } from "react";
import styles from "./landing.module.css";

const MARQUEE_ITEMS = [
  "Field Operations Platform",
  "Project Intelligence & Field Tracking",
  "Walk Verification",
  "Job Closeout",
  "Field-to-Office Sync",
  "As-Built Markup",
  "Crew Management",
  "Fiber Plant Tracking",
  "Condition Flags",
];

export default function LandingPage() {
  useEffect(() => {
    const fadeEls = document.querySelectorAll<HTMLElement>(
      `.${styles.fadeIn}`,
    );
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e, i) => {
          if (e.isIntersecting) {
            const el = e.target as HTMLElement;
            setTimeout(
              () => el.classList.add(styles.fadeInVisible),
              i * 80,
            );
            observer.unobserve(el);
          }
        });
      },
      { threshold: 0.1 },
    );
    fadeEls.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const marqueeDup = [...MARQUEE_ITEMS, ...MARQUEE_ITEMS];

  return (
    <div className={styles.root}>
      <nav className={styles.nav}>
        <Link href="/" className={styles.navLogo} aria-label="Home">
          <div className={styles.navLogoMark}>
            <svg viewBox="0 0 16 16" fill="#0a0c0f" aria-hidden>
              <path d="M8 1L14 4.5V11.5L8 15L2 11.5V4.5L8 1Z" />
            </svg>
          </div>
          <span className={styles.navLogoName}>{"\u00A0"}</span>
        </Link>
        <ul className={styles.navLinks}>
          <li>
            <a href="#features">Features</a>
          </li>
          <li>
            <a href="#workflow">Workflow</a>
          </li>
          <li>
            <a href="#dashboard">Dashboard</a>
          </li>
          <li>
            <a href="#access">Access</a>
          </li>
        </ul>
        <div className={styles.navCta}>
          <Link href="/projects" className={styles.btnGhost}>
            Sign In
          </Link>
          <Link href="/projects" className={styles.btnPrimary}>
            Request Demo
          </Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <div className={styles.heroGridBg} />
        <div className={styles.heroGlow} />
        <div className={styles.heroGlow2} />
        <div className={styles.heroInner}>
          <div>
            <div className={styles.heroEyebrow}>
              Field Operations Platform · Project Intelligence &amp; Field
              Tracking
            </div>
            <h1 className={styles.heroTitle}>
              <span>FIELD</span>
              <span className={styles.line2}>OPS.</span>
              <span className={styles.line3}>
                FIELD <span className={styles.accent}>VERIFIED.</span> OFFICE{" "}
                <span className={styles.accent}>READY.</span>
              </span>
            </h1>
            <p className={styles.heroSubtitle}>
              The end-to-end <strong>field operations platform</strong> — capture
              real conditions in the field, sync intelligence to the office, and
              close jobs without chasing paperwork.
            </p>
            <div className={styles.heroActions}>
              <Link href="/projects" className={styles.btnHero}>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  aria-hidden
                >
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M13 12H3" />
                </svg>
                Access Your Portal
              </Link>
              <a href="#workflow" className={styles.btnHeroOutline}>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                >
                  <circle cx="12" cy="12" r="10" />
                  <path d="M10 8l6 4-6 4V8z" fill="currentColor" />
                </svg>
                See How It Works
              </a>
            </div>
            <div className={styles.heroStats}>
              <div>
                <div className={styles.heroStatNum}>4×</div>
                <div className={styles.heroStatLabel}>Faster Closeouts</div>
              </div>
              <div>
                <div className={styles.heroStatNum}>100%</div>
                <div className={styles.heroStatLabel}>Field-Verified</div>
              </div>
              <div>
                <div className={styles.heroStatNum}>0</div>
                <div className={styles.heroStatLabel}>Lost Updates</div>
              </div>
            </div>
          </div>

          <div className={styles.heroVisual}>
            <div className={styles.mapCard}>
              <div className={styles.mapHeader}>
                <div className={styles.mapHeaderLeft}>
                  <div className={`${styles.dot} ${styles.dotR}`} />
                  <div className={`${styles.dot} ${styles.dotY}`} />
                  <div className={`${styles.dot} ${styles.dotG}`} />
                  <span className={styles.mapTitleBar}>
                    JOB #2847 — SECTOR 4 / WALK ACTIVE
                  </span>
                </div>
                <div className={styles.mapStatusPill}>● LIVE</div>
              </div>
              <div className={styles.mapBody}>
                <svg
                  className={styles.mapSvg}
                  viewBox="0 0 560 340"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden
                >
                  <rect width="560" height="340" fill="#0f1520" />
                  <line
                    x1="0"
                    y1="80"
                    x2="560"
                    y2="80"
                    stroke="#1a2035"
                    strokeWidth="12"
                  />
                  <line
                    x1="0"
                    y1="180"
                    x2="560"
                    y2="180"
                    stroke="#1a2035"
                    strokeWidth="8"
                  />
                  <line
                    x1="0"
                    y1="270"
                    x2="560"
                    y2="270"
                    stroke="#1a2035"
                    strokeWidth="12"
                  />
                  <line
                    x1="80"
                    y1="0"
                    x2="80"
                    y2="340"
                    stroke="#1a2035"
                    strokeWidth="8"
                  />
                  <line
                    x1="200"
                    y1="0"
                    x2="200"
                    y2="340"
                    stroke="#1a2035"
                    strokeWidth="12"
                  />
                  <line
                    x1="360"
                    y1="0"
                    x2="360"
                    y2="340"
                    stroke="#1a2035"
                    strokeWidth="8"
                  />
                  <line
                    x1="480"
                    y1="0"
                    x2="480"
                    y2="340"
                    stroke="#1a2035"
                    strokeWidth="12"
                  />
                  <rect
                    x="85"
                    y="85"
                    width="110"
                    height="90"
                    fill="#131b2e"
                    rx="2"
                  />
                  <rect
                    x="205"
                    y="85"
                    width="150"
                    height="90"
                    fill="#131b2e"
                    rx="2"
                  />
                  <rect
                    x="365"
                    y="85"
                    width="110"
                    height="90"
                    fill="#131b2e"
                    rx="2"
                  />
                  <rect
                    x="85"
                    y="185"
                    width="110"
                    height="80"
                    fill="#131b2e"
                    rx="2"
                  />
                  <rect
                    x="205"
                    y="185"
                    width="150"
                    height="80"
                    fill="#131b2e"
                    rx="2"
                  />
                  <rect
                    x="365"
                    y="185"
                    width="110"
                    height="80"
                    fill="#131b2e"
                    rx="2"
                  />
                  <path
                    d="M40 80 L80 80 L80 130 L200 130 L200 80 L360 80 L360 130 L480 130 L480 80 L560 80"
                    stroke="#2563eb"
                    strokeWidth="2"
                    fill="none"
                    strokeDasharray="6 4"
                    opacity="0.6"
                  />
                  <path
                    d="M200 130 L200 180 L360 180"
                    stroke="#2563eb"
                    strokeWidth="2"
                    fill="none"
                    strokeDasharray="6 4"
                    opacity="0.6"
                  />
                  <path
                    d="M80 80 L80 270 L200 270"
                    stroke="#ff3d3d"
                    strokeWidth="2.5"
                    fill="none"
                    strokeDasharray="8 3"
                  />
                  <path
                    d="M200 270 L360 270 L360 185"
                    stroke="#ff3d3d"
                    strokeWidth="2.5"
                    fill="none"
                  />
                  <path
                    d="M360 185 L480 185 L480 270"
                    stroke="#ff3d3d"
                    strokeWidth="2"
                    fill="none"
                  />
                  <path
                    d="M80 80 L200 80"
                    stroke="#22c55e"
                    strokeWidth="3"
                    fill="none"
                  />
                  <path
                    d="M40 80 L80 80"
                    stroke="#22c55e"
                    strokeWidth="3"
                    fill="none"
                  />
                  <circle
                    cx="80"
                    cy="80"
                    r="7"
                    fill="#22c55e"
                    stroke="#0f1520"
                    strokeWidth="2"
                  />
                  <circle
                    cx="200"
                    cy="80"
                    r="7"
                    fill="#22c55e"
                    stroke="#0f1520"
                    strokeWidth="2"
                  />
                  <circle
                    cx="360"
                    cy="80"
                    r="7"
                    fill="#22c55e"
                    stroke="#0f1520"
                    strokeWidth="2"
                  />
                  <circle
                    cx="80"
                    cy="270"
                    r="7"
                    fill="#e8ff47"
                    stroke="#0f1520"
                    strokeWidth="2"
                  />
                  <circle
                    cx="200"
                    cy="270"
                    r="7"
                    fill="#ff3d3d"
                    stroke="#0f1520"
                    strokeWidth="2"
                    opacity="0.85"
                  />
                  <circle
                    cx="360"
                    cy="185"
                    r="7"
                    fill="#ff3d3d"
                    stroke="#0f1520"
                    strokeWidth="2"
                    opacity="0.85"
                  />
                  <circle
                    cx="360"
                    cy="270"
                    r="12"
                    fill="none"
                    stroke="#e8ff47"
                    strokeWidth="2"
                    opacity="0.5"
                  >
                    <animate
                      attributeName="r"
                      values="12;18;12"
                      dur="2s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="0.5;0.1;0.5"
                      dur="2s"
                      repeatCount="indefinite"
                    />
                  </circle>
                  <circle
                    cx="360"
                    cy="270"
                    r="6"
                    fill="#e8ff47"
                    stroke="#0f1520"
                    strokeWidth="2"
                  />
                  <rect
                    x="148"
                    y="62"
                    width="42"
                    height="15"
                    rx="3"
                    fill="#ff3d3d"
                    opacity="0.9"
                  />
                  <text
                    x="169"
                    y="73"
                    textAnchor="middle"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="white"
                    fontWeight="bold"
                  >
                    MISS
                  </text>
                  <rect
                    x="296"
                    y="254"
                    width="52"
                    height="15"
                    rx="3"
                    fill="#e8ff47"
                  />
                  <text
                    x="322"
                    y="265"
                    textAnchor="middle"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="#0a0c0f"
                    fontWeight="bold"
                  >
                    VERIFY
                  </text>
                  <line
                    x1="20"
                    y1="310"
                    x2="40"
                    y2="310"
                    stroke="#22c55e"
                    strokeWidth="2.5"
                  />
                  <text
                    x="44"
                    y="314"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="#9ca3af"
                  >
                    Verified
                  </text>
                  <line
                    x1="90"
                    y1="310"
                    x2="110"
                    y2="310"
                    stroke="#ff3d3d"
                    strokeWidth="2.5"
                  />
                  <text
                    x="114"
                    y="314"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="#9ca3af"
                  >
                    Flag
                  </text>
                  <line
                    x1="160"
                    y1="310"
                    x2="180"
                    y2="310"
                    stroke="#2563eb"
                    strokeWidth="2"
                    strokeDasharray="4 2"
                  />
                  <text
                    x="184"
                    y="314"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="#9ca3af"
                  >
                    Existing
                  </text>
                  <circle cx="244" cy="310" r="4" fill="#e8ff47" />
                  <text
                    x="252"
                    y="314"
                    fontFamily="monospace"
                    fontSize="8"
                    fill="#9ca3af"
                  >
                    Technician
                  </text>
                </svg>

                <div className={styles.mapOverlayBar}>
                  <div className={styles.mapOverlayInfo}>
                    <strong>JOB-2847 · MAIN ST FIBER EXTENSION</strong>
                    2.4mi walked · 3 flags · 1 tech active
                  </div>
                  <div className={styles.mapBadge}>2 FLAGS PENDING</div>
                </div>
              </div>
            </div>

            <div className={`${styles.annoCard} ${styles.annoCard1}`}>
              <div className={styles.annoLabel}>Flag Type</div>
              <div className={`${styles.annoVal} ${styles.annoValRed}`}>
                Conduit Missing
              </div>
            </div>
            <div className={`${styles.annoCard} ${styles.annoCard2}`}>
              <div className={styles.annoLabel}>Walk Progress</div>
              <div className={`${styles.annoVal} ${styles.annoValYellow}`}>
                71% Complete
              </div>
            </div>
            <div className={`${styles.annoCard} ${styles.annoCard3}`}>
              <div className={styles.annoLabel}>Segment Status</div>
              <div className={`${styles.annoVal} ${styles.annoValGreen}`}>
                ✓ Verified
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className={styles.marqueeStrip}>
        <div className={styles.marqueeTrack}>
          {marqueeDup.map((label, i) => (
            <span key={`${label}-${i}`} className={styles.marqueeItem}>
              {label}
            </span>
          ))}
        </div>
      </div>

      <section className={`${styles.section} ${styles.featuresSection}`} id="features">
        <div className={styles.sectionInner}>
          <div className={styles.featuresHeader}>
            <div>
              <div className={styles.sectionEyebrow}>Core Platform</div>
              <h2 className={styles.sectionTitle}>
                EVERYTHING YOUR
                <br />
                <em>CREW NEEDS</em>
              </h2>
            </div>
            <p className={styles.sectionDesc}>
              Built from the ground up for field operations — not adapted from
              generic field service software. Every feature maps to how your crews
              actually work.
            </p>
          </div>

          <div className={styles.featuresGrid}>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>🗺️</div>
              <span className={styles.featureNum}>01</span>
              <div className={styles.featureName}>INTERACTIVE MAP REVIEW</div>
              <p className={styles.featureDesc}>
                Mark up drawings directly on an interactive map. Draw routes, flag
                discrepancies, annotate conduit and cable runs — in real time from
                the field or the office review panel.
              </p>
            </div>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>🚶</div>
              <span className={styles.featureNum}>02</span>
              <div className={styles.featureName}>FIELD WALK WORKFLOW</div>
              <p className={styles.featureDesc}>
                Technicians walk segments and mark verified or flagged from mobile.
                Office teams see progress live and can review flags before
                closeout.
              </p>
            </div>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>📋</div>
              <span className={styles.featureNum}>03</span>
              <div className={styles.featureName}>JOB CLOSEOUT REVIEW</div>
              <p className={styles.featureDesc}>
                Structured closeout checklists keep nothing incomplete. Walk
                status, approvals, and photo documentation in one view — no more
                spreadsheet gymnastics.
              </p>
            </div>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>📍</div>
              <span className={styles.featureNum}>04</span>
              <div className={styles.featureName}>CONDITION FLAGS & PHOTOS</div>
              <p className={styles.featureDesc}>
                Field crews pin flags with typed notes and photo attachments.
                Flags carry type, severity, and resolution status for office
                decisions.
              </p>
            </div>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>🏢</div>
              <span className={styles.featureNum}>05</span>
              <div className={styles.featureName}>OFFICE DESKTOP VIEW</div>
              <p className={styles.featureDesc}>
                A dedicated office interface for project managers — map review,
                jobs pipeline, workflow transitions, and closeout approval in one
                application.
              </p>
            </div>
            <div className={`${styles.featureCard} ${styles.fadeIn}`}>
              <div className={styles.featureIcon}>📱</div>
              <span className={styles.featureNum}>06</span>
              <div className={styles.featureName}>MOBILE FIELD APP</div>
              <p className={styles.featureDesc}>
                Purpose-built mobile experience for technicians. Minimal UI,
                offline-tolerant, optimized for one-handed use. Captures exactly
                what matters in the field.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section
        className={styles.section}
        id="workflow"
        style={{ background: "var(--bg)" }}
      >
        <div className={styles.sectionInner}>
          <div className={styles.howInner}>
            <div>
              <div className={styles.sectionEyebrow}>Process</div>
              <h2 className={styles.sectionTitle}>
                HOW A
                <br />
                <em>JOB FLOWS</em>
              </h2>
              <p
                className={styles.sectionDesc}
                style={{ marginBottom: 40 }}
              >
                From job creation to final closeout, every step is tracked,
                visible, and accountable. No lost markups or mystery status.
              </p>

              <ol className={styles.stepsList}>
                <li className={styles.stepItem}>
                  <span className={styles.stepNum}>01</span>
                  <div className={styles.stepBody}>
                    <div className={styles.stepTitle}>JOB CREATED IN OFFICE</div>
                    <p className={styles.stepDesc}>
                      A project manager creates the job, assigns a crew or
                      technician, and attaches the base map. The job enters the
                      pipeline as <em>Assigned</em>.
                    </p>
                  </div>
                </li>
                <li className={styles.stepItem}>
                  <span className={styles.stepNum}>02</span>
                  <div className={styles.stepBody}>
                    <div className={styles.stepTitle}>FIELD CREW WALKS THE PLANT</div>
                    <p className={styles.stepDesc}>
                      The technician opens the job on mobile, walks each segment,
                      and marks sections verified or flagged. Photos and notes
                      attach as needed.
                    </p>
                  </div>
                </li>
                <li className={styles.stepItem}>
                  <span className={styles.stepNum}>03</span>
                  <div className={styles.stepBody}>
                    <div className={styles.stepTitle}>UPDATES ON THE MAP</div>
                    <p className={styles.stepDesc}>
                      Discrepancies between drawings and field reality are marked
                      on the live map — new routes, missing conduit, reroutes.
                      Everything geo-referenced.
                    </p>
                  </div>
                </li>
                <li className={styles.stepItem}>
                  <span className={styles.stepNum}>04</span>
                  <div className={styles.stepBody}>
                    <div className={styles.stepTitle}>OFFICE REVIEWS & APPROVES</div>
                    <p className={styles.stepDesc}>
                      The project manager reviews flags, map updates, and walk
                      status from the desktop view, then moves the job through
                      review and approval.
                    </p>
                  </div>
                </li>
                <li className={styles.stepItem}>
                  <span className={styles.stepNum}>05</span>
                  <div className={styles.stepBody}>
                    <div className={styles.stepTitle}>JOB CLOSED OUT</div>
                    <p className={styles.stepDesc}>
                      Closeout signed off. Documentation archived. Record complete
                      for handoff, billing review, or retention.
                    </p>
                  </div>
                </li>
              </ol>
            </div>

            <div className={`${styles.workflowVisual} ${styles.fadeIn}`}>
              <div className={styles.wfHeader}>Job Status Pipeline</div>
              <div className={styles.wfStages}>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#6b7280" }}
                  />
                  <span className={styles.wfStageLabel}>Unassigned</span>
                  <span className={`${styles.wfStageTag} ${styles.tagBlue}`}>
                    QUEUE
                  </span>
                </div>
                <div className={styles.wfArrow}>↓</div>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#00d4ff" }}
                  />
                  <span className={styles.wfStageLabel}>Assigned to Crew</span>
                  <span className={`${styles.wfStageTag} ${styles.tagBlue}`}>
                    DISPATCH
                  </span>
                </div>
                <div className={styles.wfArrow}>↓</div>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#e8ff47" }}
                  />
                  <span className={styles.wfStageLabel}>Walk In Progress</span>
                  <span className={`${styles.wfStageTag} ${styles.tagYellow}`}>
                    ACTIVE
                  </span>
                </div>
                <div className={styles.wfArrow}>↓</div>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#ff6b35" }}
                  />
                  <span className={styles.wfStageLabel}>Pending Office Review</span>
                  <span className={`${styles.wfStageTag} ${styles.tagOrange}`}>
                    REVIEW
                  </span>
                </div>
                <div className={styles.wfArrow}>↓</div>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#ff3d3d" }}
                  />
                  <span className={styles.wfStageLabel}>Flagged / Needs Rework</span>
                  <span className={`${styles.wfStageTag} ${styles.tagRed}`}>
                    FLAGGED
                  </span>
                </div>
                <div className={styles.wfArrow}>↓</div>
                <div className={styles.wfStage}>
                  <div
                    className={styles.wfStageDot}
                    style={{ background: "#22c55e" }}
                  />
                  <span className={styles.wfStageLabel}>Closed Out</span>
                  <span className={`${styles.wfStageTag} ${styles.tagGreen}`}>
                    COMPLETE
                  </span>
                </div>
              </div>

              <div
                style={{
                  marginTop: 28,
                  paddingTop: 20,
                  borderTop: "1px solid var(--border)",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--muted)",
                    marginBottom: 12,
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    fontWeight: 600,
                  }}
                >
                  Current Job Mix
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <div
                    style={{
                      background: "rgba(0,212,255,0.08)",
                      border: "1px solid rgba(0,212,255,0.18)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      textAlign: "center",
                      flex: 1,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "'Bebas Neue', sans-serif",
                        fontSize: 28,
                        color: "var(--accent2)",
                        lineHeight: 1,
                      }}
                    >
                      12
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        marginTop: 2,
                      }}
                    >
                      Active
                    </div>
                  </div>
                  <div
                    style={{
                      background: "rgba(255,107,53,0.08)",
                      border: "1px solid rgba(255,107,53,0.18)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      textAlign: "center",
                      flex: 1,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "'Bebas Neue', sans-serif",
                        fontSize: 28,
                        color: "var(--accent3)",
                        lineHeight: 1,
                      }}
                    >
                      5
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        marginTop: 2,
                      }}
                    >
                      Review
                    </div>
                  </div>
                  <div
                    style={{
                      background: "rgba(34,197,94,0.08)",
                      border: "1px solid rgba(34,197,94,0.18)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      textAlign: "center",
                      flex: 1,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "'Bebas Neue', sans-serif",
                        fontSize: 28,
                        color: "var(--green-mark)",
                        lineHeight: 1,
                      }}
                    >
                      38
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        marginTop: 2,
                      }}
                    >
                      Done
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.dashboardSection} id="dashboard">
        <div className={styles.dashboardHeader}>
          <div>
            <div className={styles.sectionEyebrow}>Office View</div>
            <h2 className={styles.sectionTitle}>
              YOUR PIPELINE
              <br />
              AT A <em>GLANCE</em>
            </h2>
          </div>
          <p className={styles.sectionDesc}>
            The office desktop dashboard gives project managers a real-time view
            across active jobs — less digging through email for status.
          </p>
        </div>
        <div className={styles.dashboardScroll}>
          <div className={styles.dashCards}>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>📋</div>
              <div className={styles.dashCardValue}>
                55 <span className={styles.unit}>jobs</span>
              </div>
              <div className={styles.dashCardLabel}>Total Active Jobs</div>
              <div className={`${styles.dashCardTrend} ${styles.trendUp}`}>
                ↑ 8 added this week
              </div>
            </div>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>🚶</div>
              <div className={styles.dashCardValue}>12</div>
              <div className={styles.dashCardLabel}>Walks In Progress</div>
              <div className={`${styles.dashCardTrend} ${styles.trendNeutral}`}>
                Across 4 crews
              </div>
            </div>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>🔴</div>
              <div className={styles.dashCardValue}>23</div>
              <div className={styles.dashCardLabel}>Open Flags</div>
              <div className={`${styles.dashCardTrend} ${styles.trendFlag}`}>
                ⚑ 6 flagged critical
              </div>
            </div>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>⏳</div>
              <div className={styles.dashCardValue}>5</div>
              <div className={styles.dashCardLabel}>Pending Review</div>
              <div className={`${styles.dashCardTrend} ${styles.trendFlag}`}>
                Awaiting approval
              </div>
            </div>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>✅</div>
              <div className={styles.dashCardValue}>38</div>
              <div className={styles.dashCardLabel}>Closed This Month</div>
              <div className={`${styles.dashCardTrend} ${styles.trendUp}`}>
                ↑ 12% vs last month
              </div>
            </div>
            <div className={styles.dashCard}>
              <div className={styles.dashCardIcon}>📸</div>
              <div className={styles.dashCardValue}>412</div>
              <div className={styles.dashCardLabel}>Photos Captured</div>
              <div className={`${styles.dashCardTrend} ${styles.trendNeutral}`}>
                This month
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.loginSection}`} id="access">
        <div className={styles.loginInner}>
          <div className={styles.loginLeft}>
            <div className={styles.sectionEyebrow}>Secure Access</div>
            <h2 className={styles.sectionTitle}>
              YOUR PORTAL.
              <br />
              <em>YOUR JOBS.</em>
            </h2>
            <p className={styles.loginDesc}>
              Sign in flows are being finalized. For this demo, continue straight
              to the project dashboard — the same entry point will power real
              accounts soon.
            </p>
            <p
              className={styles.loginDesc}
              style={{ fontSize: 14, opacity: 0.9 }}
            >
              Demo access routes directly to the project dashboard while account
              access is being finalized.
            </p>
            <ul className={styles.loginPerks}>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Real-time field walk status across active jobs
              </li>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Interactive map with live updates and flag locations
              </li>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Structured closeout review and approval workflow
              </li>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Jobs pipeline dashboard with status visibility
              </li>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Photo documentation and condition flag management
              </li>
              <li className={styles.loginPerk}>
                <div className={styles.perkCheck}>✓</div>
                Role-based access for office and field (coming soon)
              </li>
            </ul>
          </div>

          <div className={`${styles.loginFormCard} ${styles.fadeIn}`}>
            <div className={styles.formLogo}>
              <div className={styles.formLogoMark} />
              <span className={styles.formLogoName}>PORTAL</span>
            </div>
            <div className={styles.formTitle}>Welcome</div>
            <div className={styles.formSubtitle}>
              Field Operations Platform — continue to explore the live demo
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Link href="/projects" className={styles.btnLogin}>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  aria-hidden
                >
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M13 12H3" />
                </svg>
                Sign In
              </Link>
              <Link
                href="/projects"
                className={styles.btnHeroOutline}
                style={{
                  justifyContent: "center",
                  width: "100%",
                  padding: "15px",
                  fontSize: 15,
                }}
              >
                Request Demo
              </Link>
            </div>

            <div className={styles.formDivider}>
              <span>Demo mode</span>
            </div>

            <div className={styles.formSecure}>
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                aria-hidden
              >
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              Secured with TLS encryption · Role-based access (planned)
            </div>
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.ctaSection}`}>
        <div className={`${styles.ctaBox} ${styles.fadeIn}`}>
          <div>
            <h2 className={styles.ctaTitle}>
              READY TO CLOSE JOBS
              <br />
              <em>FASTER?</em>
            </h2>
            <p className={styles.ctaSub}>
              Get your team on one platform and replace scattered markups, status
              phone tag, and paper closeout packets with one connected platform.
            </p>
          </div>
          <div className={styles.ctaActions}>
            <Link href="/projects" className={styles.btnHero}>
              Get Started Today
            </Link>
            <Link href="/projects" className={styles.btnHeroOutline}>
              Request a Demo
            </Link>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerLogo}>
            <div className={styles.footerLogoMark} />
            <span className={styles.footerLogoName}>{"\u00A0"}</span>
          </div>
          <div className={styles.footerCopy}>
            © {new Date().getFullYear()} Field Operations Platform
          </div>
          <div className={styles.footerLinks}>
            <a href="#">Privacy</a>
            <a href="#">Terms</a>
            <a href="#">Support</a>
            <a href="mailto:hello@example.com">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
