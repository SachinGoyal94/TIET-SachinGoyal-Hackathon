// Builds the 7-slide hackathon deck: Financial Risk Intelligence Platform.
// Dark fintech theme matching the platform UI. Run: node docs/build_deck.mjs

const pptxgen = require("pptxgenjs");

const W = 13.33, H = 7.5, M = 0.5;
const BG = "050A14", SURFACE = "0E1829", CARD = "13203A", EDGE = "1B2C4D";
const TEXT = "E2E8F0", SUB = "94A3B8", MUTED = "64748B";
const ACCENT = "2DD4BF", GOOD = "10B981", WARN = "F59E0B", BAD = "F43F5E";
const FONT = "Segoe UI";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Sachin Goyal";
pres.title = "Financial Risk Intelligence Platform";

const bu = () => ({ code: "2022", indent: 10 });

function header(slide, kicker, title) {
  slide.background = { color: BG };
  slide.addText(kicker.toUpperCase(), {
    x: M, y: 0.32, w: W - 2 * M, h: 0.3, fontSize: 11, fontFace: FONT,
    color: ACCENT, charSpacing: 3, bold: true, margin: 0,
  });
  slide.addText(title, {
    x: M, y: 0.58, w: W - 2 * M, h: 0.75, fontSize: 30, fontFace: FONT,
    color: TEXT, bold: true, margin: 0,
  });
}

function card(slide, x, y, w, h) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, fill: { color: CARD }, line: { color: EDGE, width: 1 },
    rectRadius: 0.06,
  });
}

// ---------- Slide 1: Title ----------
{
  const s = pres.addSlide();
  s.background = { color: BG };
  s.addShape(pres.shapes.LINE, { x: M, y: 2.05, w: 2.2, h: 0, line: { color: ACCENT, width: 3 } });
  s.addText("Financial Risk Intelligence Platform", {
    x: M, y: 2.25, w: W - 2 * M, h: 1.6, fontSize: 47, fontFace: FONT,
    color: TEXT, bold: true, margin: 0,
  });
  s.addText("AI/NLP risk signals from news and social media, driving tactical index\nrebalancing and regulator-grade portfolio stress testing", {
    x: M, y: 3.75, w: 10.5, h: 0.9, fontSize: 17, fontFace: FONT, color: SUB, margin: 0,
  });
  s.addText([
    { text: "S&P Global & Crisil Campus Hackathon 2026", options: { color: ACCENT, bold: true, breakLine: true } },
    { text: "Sachin Goyal  ·  Thapar Institute of Engineering and Technology, Patiala", options: { color: SUB } },
  ], { x: M, y: 5.9, w: 11, h: 0.8, fontSize: 14, fontFace: FONT, margin: 0 });
  s.addText("single Docker command  ·  zero API keys  ·  every number measured on real data", {
    x: M, y: 6.85, w: 11, h: 0.35, fontSize: 12, fontFace: FONT, color: MUTED, italic: true, margin: 0,
  });
}

// ---------- Slide 2: Problem & Approach ----------
{
  const s = pres.addSlide();
  header(s, "Problem & Approach", "Risk surfaces as text first. Humans read it. Machines should too.");
  card(s, M, 1.55, 6.0, 5.3);
  s.addText("THE PROBLEM", { x: 0.85, y: 1.8, w: 5.3, h: 0.3, fontSize: 12, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  s.addText([
    { text: "Market-moving information appears first as unstructured text: a downgrade headline, a sanctions story, an angry tweet.", options: { bullet: bu(), breakLine: true } },
    { text: "Analysts read it and decide what it means - slowly, subjectively, and only during market hours.", options: { bullet: bu(), breakLine: true } },
    { text: "The case study: build an AI/NLP engine that turns news and social text into machine-readable risk signals (sentiment, event type, impact), then prove it by acting on them.", options: { bullet: bu() } },
  ], { x: 0.85, y: 2.15, w: 5.35, h: 2.6, fontSize: 14, fontFace: FONT, color: TEXT, paraSpaceAfter: 10, margin: 0 });
  s.addText("OUR APPROACH", { x: 0.85, y: 4.85, w: 5.3, h: 0.3, fontSize: 12, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  s.addText([
    { text: "Specialist models where they win: FinBERT for calibrated sentiment, a small LLM for per-entity understanding.", options: { bullet: bu(), breakLine: true } },
    { text: "Measure everything: 15 years of real news scored against real market moves.", options: { bullet: bu() } },
  ], { x: 0.85, y: 5.2, w: 5.35, h: 1.5, fontSize: 14, fontFace: FONT, color: TEXT, paraSpaceAfter: 8, margin: 0 });

  card(s, 6.9, 1.55, 5.95, 5.3);
  s.addText("WHAT THE ENGINE OUTPUTS PER HEADLINE", { x: 7.25, y: 1.8, w: 5.3, h: 0.3, fontSize: 12, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  const outputs = [
    ["Sentiment", "-1 to +1", "FinBERT, 89.4% held-out accuracy"],
    ["Event class", "6 labels", "LLM-led hybrid; survives informal text"],
    ["Impact", "1 to 10", "calibrated on 19,872 real events"],
  ];
  outputs.forEach((o, i) => {
    const y = 2.3 + i * 1.05;
    s.addShape(pres.shapes.OVAL, { x: 7.25, y: y + 0.12, w: 0.16, h: 0.16, fill: { color: ACCENT } });
    s.addText(o[0], { x: 7.55, y, w: 2.4, h: 0.35, fontSize: 15, fontFace: FONT, color: TEXT, bold: true, margin: 0 });
    s.addText(o[1], { x: 9.9, y, w: 1.2, h: 0.35, fontSize: 15, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
    s.addText(o[2], { x: 7.55, y: y + 0.34, w: 5.0, h: 0.35, fontSize: 11.5, fontFace: FONT, color: SUB, margin: 0 });
  });
  s.addText("\"russia nuked ukraine\"  ->  { sentiment: -0.49,  event: Geopolitical,  impact: 8.0 }", {
    x: 7.25, y: 5.6, w: 5.3, h: 0.5, fontSize: 12.5, fontFace: "Consolas", color: TEXT,
    italic: true, margin: 0,
  });
  s.addText("live analyzer, adversarially tested", { x: 7.25, y: 6.15, w: 5.3, h: 0.3, fontSize: 10.5, fontFace: FONT, color: MUTED, margin: 0 });
}

// ---------- Slide 3: System Design ----------
{
  const s = pres.addSlide();
  header(s, "System Design", "One engine, three layers, two downstream decisions");
  const layers = [
    ["INGESTION", "GDELT live news (15 min, keyless)  ·  91k FNSPID headlines (2009-23)  ·  10.5k real tweets  ·  synthetic fallback", ACCENT],
    ["AI/NLP RISK ENGINE", "entity matcher (aliases + cashtags)  ->  FinBERT sentiment [-1,1]  ->  per-entity LLM layer (Qwen3-4B JSON)  ->  event classifier  ->  impact = severity x conviction x corroboration", "FFFFFF"],
    ["EVENTS & DECISIONS", "24h event clusters with corroboration  ->  Module A: vol-adjusted index tilt  ·  Module B: scenario stress + CET1 flow", ACCENT],
  ];
  layers.forEach((l, i) => {
    const y = 1.6 + i * 1.32;
    card(s, M, y, 12.33, 1.12);
    s.addText(l[0], { x: 0.85, y: y + 0.12, w: 3.2, h: 0.4, fontSize: 15, fontFace: FONT, color: l[2], bold: true, margin: 0 });
    s.addText(l[1], { x: 0.85, y: y + 0.52, w: 11.2, h: 0.5, fontSize: 12.5, fontFace: FONT, color: SUB, margin: 0 });
  });
  card(s, M, 5.72, 12.33, 1.3);
  s.addText("SERVED AS ONE PROCESS", { x: 0.85, y: 5.9, w: 3.2, h: 0.35, fontSize: 13, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  s.addText("FastAPI (14 endpoints, SQLite WAL) serves both the REST API and the React dashboard on one port.  46 tests green  ·  CI on every push  ·  resumable data pipelines", {
    x: 0.85, y: 6.3, w: 11.3, h: 0.55, fontSize: 12.5, fontFace: FONT, color: SUB, margin: 0,
  });
}

// ---------- Slide 4: Implementation Highlights ----------
{
  const s = pres.addSlide();
  header(s, "Implementation Highlights", "Choices we can defend, and the evidence behind each");
  const items = [
    ["FinBERT for bulk sentiment", "Best of 5 benchmarked models on the held-out split (89.4% vs 88.6-76.9%). 110M params, 30ms on CPU - runs on the jury's laptop.", "89.4%", "held-out accuracy"],
    ["LLM for per-entity reading", "One headline can be positive for Apple, negative for Amazon. Qwen3-4B outputs per-entity JSON; human ceiling on this task is ~69%.", "72.4%", "vs 59.8% shared-score"],
    ["Impact calibrated on real data", "The data overruled our priors: firm-specific news (credit, launches) moves names more than generic geopolitics. Formula stays explainable.", "19,872", "events calibrated"],
    ["Regulator-grade stress testing", "DFAST/EBA scenarios + 5 historical replays (COVID, 2022, SVB), S&P-style rating migration, Vasicek PD, CET1 depletion and reverse stress.", "2,081", "bps COVID depletion"],
  ];
  items.forEach((it, i) => {
    const x = M + (i % 2) * 6.25, y = 1.6 + Math.floor(i / 2) * 2.75;
    card(s, x, y, 6.05, 2.55);
    s.addText(it[0], { x: x + 0.3, y: y + 0.18, w: 4.0, h: 0.6, fontSize: 15, fontFace: FONT, color: TEXT, bold: true, margin: 0 });
    s.addText(it[2], { x: x + 4.35, y: y + 0.12, w: 1.6, h: 0.7, fontSize: 26, fontFace: FONT, color: ACCENT, bold: true, align: "right", margin: 0 });
    s.addText(it[3], { x: x + 4.0, y: y + 0.72, w: 1.95, h: 0.5, fontSize: 10, fontFace: FONT, color: MUTED, align: "right", margin: 0 });
    s.addText(it[1], { x: x + 0.3, y: y + 0.85, w: 5.45, h: 1.55, fontSize: 12, fontFace: FONT, color: SUB, margin: 0 });
  });
}

// ---------- Slide 5: Key Results ----------
{
  const s = pres.addSlide();
  header(s, "Key Results", "Every number measured on real data - 15 years of news vs real market moves");
  const rows = [
    ["Sentiment accuracy (held-out labeled split)", "89.4%", "best of 5 benchmarked models"],
    ["Directional hit rate on strong signals", "55.6%", "3,605 events; literature bar 53-55%"],
    ["Credit-event market reaction", "+25.2 bps", "t = 3.01, significant at 1%"],
    ["Impact score vs realized |moves|", "IC +0.066", "19,872 real events"],
    ["Per-entity sentiment vs shared score", "72.4% vs 59.8%", "SEntFiN human-labeled benchmark"],
    ["Rebalancer vs cap-weight (2022 bear, net)", "+4.8 pts", "510-day walk-forward, 10bps costs"],
  ];
  const tableRows = rows.map(([a, b, c]) => ([
    { text: a, options: { color: TEXT, fontSize: 13.5, fontFace: FONT, fill: { color: SURFACE } } },
    { text: b, options: { color: ACCENT, fontSize: 15, bold: true, fontFace: FONT, align: "right", fill: { color: SURFACE } } },
    { text: c, options: { color: SUB, fontSize: 11, fontFace: FONT, fill: { color: SURFACE } } },
  ]));
  s.addTable(tableRows, {
    x: M, y: 1.7, w: 8.1, colW: [4.4, 1.6, 2.1],
    border: { pt: 0.5, color: EDGE }, fill: { color: SURFACE }, rowH: 0.62, valign: "middle",
  });
  card(s, 8.9, 1.7, 3.95, 5.2);
  s.addText("WHY THIS EVIDENCE MATTERS", { x: 9.2, y: 1.95, w: 3.4, h: 0.5, fontSize: 12, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  s.addText([
    { text: "No synthetic data in this table: 78k real articles + 10.5k real tweets with real timestamps, scored against real prices.", options: { bullet: bu(), breakLine: true } },
    { text: "Hit rate at/above the 53-55% bar the literature considers meaningful for daily news signals.", options: { bullet: bu(), breakLine: true } },
    { text: "We report the losing configurations too (turnover study) - measured, not marketed.", options: { bullet: bu() } },
  ], { x: 9.2, y: 2.5, w: 3.4, h: 4.2, fontSize: 12, fontFace: FONT, color: TEXT, paraSpaceAfter: 10, margin: 0 });
}

// ---------- Slide 6: Domain Impact ----------
{
  const s = pres.addSlide();
  header(s, "Domain Impact", "The same workflow pattern risk teams already trust - compressed from weeks to seconds");
  const items = [
    ["Signal", "News-to-signal automation mirrors what S&P Global Market Intelligence and RavenPack sell: entity-level, calibrated, with novelty and corroboration. Ours is open and explainable.", "NETWORK"],
    ["Scenario", "Stress testing follows the supervisory playbook (CCAR/DFAST, EBA/ICAAP): named scenarios, rating migration, Vasicek PD, CET1 depletion - the vocabulary of ICAAP submissions.", "SHIELD"],
    ["Capital", "The headline output is a CET1 depletion number in basis points with reverse stress: what would it take to breach the buffer. That is board-level language.", "LANDMARK"],
  ];
  items.forEach((it, i) => {
    const y = 1.65 + i * 1.75;
    card(s, M, y, 12.33, 1.55);
    s.addText(it[0].toUpperCase(), { x: 0.85, y: y + 0.18, w: 2.2, h: 0.4, fontSize: 16, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
    s.addText(it[1], { x: 0.85, y: y + 0.6, w: 11.2, h: 0.85, fontSize: 12.5, fontFace: FONT, color: SUB, margin: 0 });
  });
  s.addText("Built for the wholesale-banking and ratings domain: credit terminology exact, transition matrices from S&P's published study, scenarios from the Fed and EBA.", {
    x: M, y: 7.0, w: 12.3, h: 0.35, fontSize: 11.5, fontFace: FONT, color: MUTED, italic: true, margin: 0,
  });
}

// ---------- Slide 7: Limitations & Next Steps ----------
{
  const s = pres.addSlide();
  header(s, "Limitations & Next Steps", "What we would build with more time - and what we would measure first");
  card(s, M, 1.6, 6.0, 5.3);
  s.addText("HONEST LIMITATIONS", { x: 0.85, y: 1.85, w: 5.3, h: 0.3, fontSize: 12, fontFace: FONT, color: WARN, bold: true, margin: 0 });
  s.addText([
    { text: "Shock calibration is illustrative, not supervisory-grade in magnitude fitting.", options: { bullet: bu(), breakLine: true } },
    { text: "Event clustering is rule-based (entity + type + 24h); embedding similarity would deduplicate better.", options: { bullet: bu(), breakLine: true } },
    { text: "Impact IC of 0.066 is modest by design: daily-horizon news signals live in the 0.5-2% R2 zone.", options: { bullet: bu(), breakLine: true } },
    { text: "The rebalancer trailed equal-weight in 2022; it beats its own benchmark, not every factor.", options: { bullet: bu() } },
  ], { x: 0.85, y: 2.2, w: 5.35, h: 4.5, fontSize: 13, fontFace: FONT, color: TEXT, paraSpaceAfter: 10, margin: 0 });
  card(s, 6.9, 1.6, 5.95, 5.3);
  s.addText("NEXT STEPS", { x: 7.25, y: 1.85, w: 5.3, h: 0.3, fontSize: 12, fontFace: FONT, color: ACCENT, bold: true, margin: 0 });
  s.addText([
    { text: "Intraday event windows with per-minute price data for tighter impact measurement.", options: { bullet: bu(), breakLine: true } },
    { text: "Fine-tune the event classifier on a labeled corpus (accuracy currently unmeasured - the one honest gap).", options: { bullet: bu(), breakLine: true } },
    { text: "Embedding-based deduplication and novelty scoring for event clustering.", options: { bullet: bu(), breakLine: true } },
    { text: "Streaming architecture (Kafka + point-in-time store) behind the same repository interfaces.", options: { bullet: bu(), breakLine: true } },
    { text: "Extend the universe beyond 14 names and add Indian markets (Crisil coverage).", options: { bullet: bu() } },
  ], { x: 7.25, y: 2.2, w: 5.35, h: 4.5, fontSize: 13, fontFace: FONT, color: TEXT, paraSpaceAfter: 10, margin: 0 });
  s.addText("All code, evidence artifacts and measurement scripts: public repository, MIT licensed.", {
    x: M, y: 7.0, w: 12.3, h: 0.35, fontSize: 11.5, fontFace: FONT, color: MUTED, italic: true, margin: 0,
  });
}

pres.writeFile({ fileName: "docs/deck_build/presentation.pptx" }).then(() => console.log("deck written"));
