from __future__ import annotations

import json
import hashlib
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from alphaledger.alpaca_normalize import normalize_option_chain
from alphaledger.alpaca_readonly import ReadOnlyResponse
from alphaledger.demo import build_account, build_snapshot, demo_prices
from alphaledger.engine import GovernedTradingEngine
from alphaledger.evaluation import run_options_replay
from alphaledger.evaluation_demo import build_frozen_options_replay
from alphaledger.ledger import EvidenceLedger
from alphaledger.models import RiskPolicy
from alphaledger.advisory import OpenAIOptionsAdvisory
from alphaledger.options import (
    GovernedOptionsEngine,
    TemplateOptionsAdvisory,
    UnavailableOptionsAdvisory,
)
from alphaledger.options_demo import build_options_account, build_options_chain
from alphaledger.replay import replay_controls
from alphaledger.competition import CompetitionRiskPolicy, CompetitionWindow


def _fixture_response(endpoint: str, path: Path) -> ReadOnlyResponse:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ReadOnlyResponse(
        endpoint=endpoint,
        observed_at="2026-08-24T12:00:00+00:00",
        request_id="frozen-fixture",
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        record_count=len(payload.get("snapshots", payload.get("option_contracts", [payload]))),
        payload=payload,
    )


st.set_page_config(page_title="AxiomWeave AlphaLedger", page_icon="🧬", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.25rem; padding-bottom: 3rem;}
      [data-testid="stMetricValue"] {font-size: 1.65rem;}
      .gate-ok {background:#0c2e34;border:1px solid #36d7c7;color:#f5f7fa;padding:1rem;border-radius:12px;}
      .gate-stop {background:#341d24;border:1px solid #ff8b9a;color:#f5f7fa;padding:1rem;border-radius:12px;}
      .small-note {color:#9ca9b6;font-size:.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.image(str(ROOT / "assets" / "alphaledger-cover.png"), width="stretch")
st.title("Proof before profit")
st.caption(
    "An abstention-first, defined-risk options agent for Alpaca paper trading. "
    "AI advice may veto but can never authorize; deterministic evidence and risk gates have final authority."
)

if "shared_ledger" not in st.session_state:
    st.session_state.shared_ledger = EvidenceLedger()
if "engine" not in st.session_state:
    st.session_state.engine = GovernedTradingEngine(ledger=st.session_state.shared_ledger)
if "options_engine" not in st.session_state:
    st.session_state.options_engine = GovernedOptionsEngine(ledger=st.session_state.shared_ledger)
if "result" not in st.session_state:
    st.session_state.result = None
if "options_result" not in st.session_state:
    st.session_state.options_result = None

competition_tab, options_tab, ledger_tab, evaluation_tab, equity_tab, replay_tab, packet_tab = st.tabs(
    [
        "Competition control",
        "Options agent",
        "Evidence ledger",
        "Evaluation readiness",
        "Equity baseline",
        "Replay & controls",
        "AxiomWeave packet",
    ]
)

with competition_tab:
    window = CompetitionWindow()
    competition_policy = CompetitionRiskPolicy()
    now_utc = datetime.now(timezone.utc)
    phase = window.phase_at(now_utc)
    st.subheader("Four sessions. One writer. Every action proven.")
    st.caption(
        "The public panel is clock-and-policy only. It has no Alpaca credentials, no account ID, "
        "no broker adapter, and no private runtime journal."
    )
    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("Current phase", phase.value.replace("_", " ").upper())
    cm2.metric("New entries", "10:20–14:30 ET")
    cm3.metric("Max plan loss", f"${competition_policy.max_loss_per_plan_usd:,.0f}")
    cm4.metric("Default flat", "Thu 15:45 ET")

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.markdown("#### Organizer window → deterministic controller")
        st.dataframe(
            [
                {"boundary": "P&L begins", "time": "Mon Aug 31 · 09:30 ET", "behavior": "observe only"},
                {"boundary": "Entry opens", "time": "Mon–Thu · 10:20 ET", "behavior": "one gated attempt/day"},
                {"boundary": "Entry closes", "time": "Mon–Thu · 14:30 ET", "behavior": "exit only"},
                {"boundary": "Force flat", "time": "Thu Sep 3 · 15:45 ET", "behavior": "close + reconcile"},
                {"boundary": "Raw equity", "time": "Fri Sep 4 · 09:30 ET", "behavior": "record and stop"},
            ],
            hide_index=True,
            width="stretch",
        )
        st.markdown(
            "**Controller path:** exact account pin → current positions/orders → fresh SPY bars → "
            "directional call/put spread → deterministic options gate → official Alpaca CLI → "
            "status reconciliation → hash-linked receipt."
        )
        st.warning(
            "Organizer wording confirms a raw-equity snapshot but does not yet resolve Friday "
            "pre-open option marks or Thursday-expiry settlement. The hold-through-cutoff override "
            "therefore remains disabled."
        )
    with right:
        st.markdown("#### Frozen capital policy")
        st.json(
            {
                "paper_only": True,
                "underlying": "SPY",
                "maximum_open_plans": competition_policy.max_open_plans,
                "maximum_entries_per_day": competition_policy.max_entries_per_session,
                "maximum_plan_loss_usd": competition_policy.max_loss_per_plan_usd,
                "daily_stop_usd": competition_policy.max_daily_drawdown_usd,
                "total_drawdown_stop_usd": competition_policy.max_total_drawdown_usd,
                "take_profit": f"{competition_policy.take_profit_fraction:.0%}",
                "stop_loss": f"{competition_policy.stop_loss_fraction:.0%}",
                "maximum_hold_minutes": int(competition_policy.max_hold_hours * 60),
            }
        )
        st.markdown("#### Strategy evidence ceiling")
        benchmark_path = ROOT / "evidence" / "signal-benchmark-receipt.json"
        if benchmark_path.exists():
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
            fallback = benchmark.get("exploratory_fallback", {})
            held_out = fallback.get("held_out_gross", {})
            st.error("PROMOTION: REFUSED")
            st.write(
                "No tested route cleared the held-out promotion gate. The one daily attempt is "
                "explicitly C0 exploratory, not proven alpha."
            )
            st.caption(
                f"Least-weak proxy: {fallback.get('entry_policy', 'n/a')} · threshold "
                f"{fallback.get('threshold', 'n/a')} · {fallback.get('horizon', 'n/a')} · "
                f"held-out n={held_out.get('trades', 'n/a')} · mean="
                f"{held_out.get('mean_signed_return_bps', 'n/a')} bps."
            )
        st.caption(
            "C1 proves deterministic mechanics and falsifiers. C2 covers the authenticated organizer "
            "window. Profitability, future fills, and winning probability remain C0."
        )

with options_tab:
    st.subheader("Defined-risk options decision")
    st.caption(
        "The public path creates a validated Alpaca multi-leg paper-order payload but never sends it. "
        "Every scenario changes one falsifiable fact."
    )
    option_left, option_right = st.columns([0.8, 1.2], gap="large")
    with option_left:
        option_scenario = st.selectbox(
            "Options falsifier",
            [
                "Valid defined-risk spread",
                "Stale underlying snapshot",
                "Stale option evidence",
                "Missing Greeks",
                "Wide bid-ask market",
                "Maximum loss above budget",
                "Low open interest",
                "No valid vertical",
                "Injected live broker mode",
                "Unreconciled options order",
            ],
        )
        use_openai = st.toggle(
            "Use optional OpenAI structured advisory",
            value=False,
            help=(
                "Requires OPENAI_API_KEY and ALPHALEDGER_ADVISORY_MODEL in the private runtime. "
                "No account data or credentials are sent."
            ),
        )
        st.info(
            "Frozen synthetic chain, one contract, maximum-loss budget $25. "
            "Broker authentication is neither requested nor stored."
        )
        if st.button("Run options evidence cycle", type="primary", width="stretch"):
            if use_openai:
                try:
                    st.session_state.options_engine.advisory = OpenAIOptionsAdvisory()
                except RuntimeError:
                    st.session_state.options_engine.advisory = UnavailableOptionsAdvisory()
                    st.warning("AI advisory is unavailable, so the cycle will fail closed.")
            else:
                st.session_state.options_engine.advisory = TemplateOptionsAdvisory()

            chain_scenario = (
                "Valid defined-risk spread"
                if option_scenario in {"Injected live broker mode", "Unreconciled options order"}
                else option_scenario
            )
            chain = build_options_chain(chain_scenario)
            account = build_options_account(
                broker_mode="live" if option_scenario == "Injected live broker mode" else "simulation",
                open_orders=1 if option_scenario == "Unreconciled options order" else 0,
            )
            st.session_state.options_result = st.session_state.options_engine.run_cycle(chain, account)

    with option_right:
        option_result = st.session_state.options_result
        if option_result is None:
            st.write("Run the valid spread, then flip one falsifier to prove deterministic refusal.")
        else:
            om1, om2, om3, om4 = st.columns(4)
            om1.metric(
                "Strategy",
                "CALL DEBIT" if option_result.thesis.strategy == "bull_call_debit_spread" else "CASH",
            )
            om2.metric("Maximum loss", f"${option_result.risk.projected_max_loss:,.2f}")
            om3.metric("Risk gate", "PASS" if option_result.risk.approved else "ABSTAIN")
            om4.metric(
                "Receipt",
                "SIMULATED" if option_result.receipt.status == "simulated_plan" else "ABSTAIN",
            )

            option_gate_class = "gate-ok" if option_result.risk.approved else "gate-stop"
            option_gate_title = "Validated simulation plan" if option_result.risk.approved else "Execution blocked"
            st.markdown(
                f'<div class="{option_gate_class}"><b>{option_gate_title}</b><br>'
                f'{"<br>".join(option_result.risk.reasons)}</div>',
                unsafe_allow_html=True,
            )

            if option_result.thesis.legs:
                st.markdown("#### Defined-risk structure")
                st.dataframe(
                    [
                        {
                            "contract": leg.contract.symbol,
                            "action": leg.position_intent,
                            "strike": f"${leg.contract.strike_price:,.2f}",
                            "bid / ask": f"${leg.contract.bid_price:.2f} / ${leg.contract.ask_price:.2f}",
                            "delta": "missing" if leg.contract.delta is None else f"{leg.contract.delta:.2f}",
                            "IV": (
                                "missing"
                                if leg.contract.implied_volatility is None
                                else f"{leg.contract.implied_volatility:.1%}"
                            ),
                            "open interest": leg.contract.open_interest,
                        }
                        for leg in option_result.thesis.legs
                    ],
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    f"Net debit USD {option_result.thesis.net_debit_per_share:.2f} per share · "
                    f"capped maximum loss USD {option_result.thesis.max_loss_dollars:.2f} · "
                    f"capped maximum profit USD {option_result.thesis.max_profit_dollars:.2f}."
                )

            st.markdown("#### Advisory critic")
            st.write(option_result.advisory.summary)
            st.caption(f"Source: {option_result.advisory.source} · Falsifier: {option_result.advisory.falsifier}")
            with st.expander("Structured Alpaca order plan and full receipt"):
                st.json(option_result.to_dict())

with equity_tab:
    st.subheader("Simplest strong baseline")
    st.caption("The original SPY long-or-cash path remains as a negative-control architecture, not the competition track.")
    left, right = st.columns([0.8, 1.2], gap="large")
    with left:
        st.subheader("1. Choose a falsifier")
        scenario = st.selectbox(
            "Demo scenario",
            [
                "Valid bounded candidate",
                "Stale market evidence",
                "Daily-loss stop",
                "Unreconciled open order",
                "Flat signal — abstain",
            ],
        )
        max_new_notional = st.slider("Maximum new notional", 5.0, 25.0, 25.0, 5.0, format="$%.0f")
        st.info("Public demo mode is simulation-only. Broker credentials are neither requested nor stored.")

        if st.button("Run governed cycle", type="primary", width="stretch"):
            prices = demo_prices()
            snapshot = build_snapshot(prices)
            account = build_account()
            if scenario == "Stale market evidence":
                snapshot = replace(snapshot, data_age_seconds=900)
            elif scenario == "Daily-loss stop":
                account = build_account(daily_pnl=-10.0)
            elif scenario == "Unreconciled open order":
                account = build_account(open_orders=1)
            elif scenario == "Flat signal — abstain":
                snapshot = build_snapshot([100.0] * 90)

            policy = RiskPolicy(max_new_notional=max_new_notional)
            st.session_state.result = st.session_state.engine.run_cycle(snapshot, account, policy)

    with right:
        st.subheader("2. Inspect the decision path")
        result = st.session_state.result
        if result is None:
            st.write("Run a cycle to produce a thesis, skeptic verdict, risk decision, and hash-linked receipt.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Candidate", result.thesis.side.upper())
            m2.metric("New notional", f"${result.risk.projected_new_notional:,.2f}")
            m3.metric("Risk gate", "PASS" if result.risk.approved else "ABSTAIN")
            m4.metric("Receipt", result.receipt.status.upper())

            gate_class = "gate-ok" if result.risk.approved else "gate-stop"
            gate_title = "Approved for simulation" if result.risk.approved else "Execution blocked"
            st.markdown(
                f'<div class="{gate_class}"><b>{gate_title}</b><br>{"<br>".join(result.risk.reasons)}</div>',
                unsafe_allow_html=True,
            )

            st.markdown("#### Falsifiable thesis")
            st.write(result.thesis.rationale)
            st.caption("Invalidation: " + result.thesis.invalidation_condition)
            with st.expander("Structured cycle receipt"):
                st.json(result.to_dict())

with ledger_tab:
    ledger = st.session_state.shared_ledger
    verified, failures = ledger.verify()
    a, b, c = st.columns(3)
    a.metric("Recorded decisions", len(ledger.entries))
    b.metric("Chain integrity", "VERIFIED" if verified else "FAILED")
    c.metric("Current head", ledger.head_hash[:12] + "…")
    st.caption("The local hash chain is tamper-evident; repository history is required for durable review.")
    if failures:
        st.error(" | ".join(failures))
    for entry in reversed(ledger.entries):
        with st.expander(
            f"#{entry['sequence']} · {entry['payload']['receipt']['status']} · {entry['entry_hash'][:12]}…"
        ):
            st.json(entry)

with evaluation_tab:
    st.subheader("Frozen evaluation and broker-observation boundaries")
    st.caption(
        "The organizer window is fixed at Aug 31 09:30 ET through Sep 4 09:30 ET. "
        "Historical replay remains a mechanics control; real-time Alpaca observation is the "
        "competition route, with paper submission still separately locked."
    )
    episodes, replay_manifest = build_frozen_options_replay()
    options_replay_receipt = run_options_replay(episodes, replay_manifest)

    route_left, route_right = st.columns(2, gap="large")
    with route_left:
        st.markdown("#### Historical replay control")
        st.success(
            f"Manifest {replay_manifest.manifest_id} · {len(episodes)} frozen episodes · "
            f"input digest {replay_manifest.episodes_sha256[:12]}…"
        )
        st.write(
            "A changed observation fails the manifest. The unguarded proposer, cash, and fixed-seed "
            "shuffled settlements remain visible controls."
        )
    with route_right:
        st.markdown("#### Competition paper-observation boundary")
        st.info(
            "Named GET-only methods: paper account, positions, open orders, stock snapshot, option "
            "contracts, and option-chain snapshots. Redirects and non-paper trading hosts are rejected."
        )
        st.write(
            "No credential field exists in this dashboard, and the observer has not been run. "
            "Kickoff reconciliation produces a redacted receipt with no account ID or secret headers."
        )

    fixture_root = ROOT / "tests" / "fixtures"
    normalized_fixture = normalize_option_chain(
        "SPY",
        _fixture_response(
            "https://data.alpaca.markets/v2/stocks/SPY/snapshot",
            fixture_root / "alpaca_stock_snapshot.json",
        ),
        _fixture_response(
            "https://paper-api.alpaca.markets/v2/options/contracts",
            fixture_root / "alpaca_option_contracts.json",
        ),
        _fixture_response(
            "https://data.alpaca.markets/v1beta1/options/snapshots/SPY",
            fixture_root / "alpaca_option_chain.json",
        ),
        as_of=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        stock_feed="iex",
        options_feed="indicative",
    )
    normalized_result = GovernedOptionsEngine().run_cycle(
        normalized_fixture.chain,
        build_options_account(broker_mode="paper"),
    )
    st.markdown("#### Frozen Alpaca-shape bridge check")
    bridge_a, bridge_b, bridge_c, bridge_d = st.columns(4)
    bridge_a.metric("Typed contracts", len(normalized_fixture.chain.contracts))
    bridge_b.metric("Feeds", "IEX + INDICATIVE")
    bridge_c.metric("Risk gate", "PASS" if normalized_result.risk.approved else "ABSTAIN")
    bridge_d.metric("Maximum loss", f"${normalized_result.risk.projected_max_loss:,.2f}")
    st.caption(
        "STOCK SNAPSHOT + CONTRACT CATALOG + OPTION CHAIN → strict normalizer → deterministic policy. "
        "Frozen fixtures only; no credential or network request was made."
    )

    st.markdown("#### Frozen synthetic replay receipt")
    st.dataframe(
        [
            {
                "route": metric.route,
                "plans": metric.plans,
                "abstentions": metric.abstentions,
                "synthetic realized P&L": f"${metric.synthetic_realized_pnl:,.2f}",
                "maximum drawdown": f"{metric.maximum_drawdown:.2%}",
                "worst episode": f"${metric.worst_episode_pnl:,.2f}",
                "modeled loss exposed": f"${metric.total_modeled_maximum_loss:,.2f}",
            }
            for metric in options_replay_receipt.metrics
        ],
        hide_index=True,
        width="stretch",
    )
    st.warning(
        "C1 only: these deliberately synthetic payoffs test replay mechanics and controls. They are "
        "not market evidence, expected returns, or the official hackathon evaluation."
    )

    st.markdown("#### Frozen read-only Alpaca surface")
    st.dataframe(
        [
            {"purpose": "account state", "method": "GET", "endpoint": "paper-api.alpaca.markets/v2/account"},
            {"purpose": "positions", "method": "GET", "endpoint": "paper-api.alpaca.markets/v2/positions"},
            {"purpose": "open-order reconciliation", "method": "GET", "endpoint": "paper-api.alpaca.markets/v2/orders?status=open"},
            {"purpose": "underlying stock snapshot", "method": "GET", "endpoint": "data.alpaca.markets/v2/stocks/SPY/snapshot"},
            {"purpose": "option contracts", "method": "GET", "endpoint": "paper-api.alpaca.markets/v2/options/contracts"},
            {"purpose": "quotes + Greeks", "method": "GET", "endpoint": "data.alpaca.markets/v1beta1/options/snapshots/SPY"},
        ],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Manifest and replay receipt"):
        st.json(options_replay_receipt.to_dict())

with replay_tab:
    st.subheader("Frozen replay against controls")
    st.caption(
        "These deterministic synthetic results test mechanics only. They are not market evidence or a return forecast."
    )
    prices = demo_prices()
    st.line_chart({"synthetic SPY-like price": prices})
    metrics = replay_controls(prices)
    st.dataframe(
        [
            {
                "route": metric.name,
                "total return": f"{metric.total_return:.2%}",
                "max drawdown": f"{metric.max_drawdown:.2%}",
                "turnover events": metric.turnover_events,
            }
            for metric in metrics
        ],
        width="stretch",
        hide_index=True,
    )
    st.warning("Promotion gate: held-out paper evidence and independent review are still required.")

with packet_tab:
    competition_packet_path = ROOT / "evidence" / "competition-window-decision.json"
    competition_packet = json.loads(competition_packet_path.read_text(encoding="utf-8"))
    st.subheader("Current competition decision")
    st.json(competition_packet)
    st.divider()
    st.subheader("Historical build-stage packets")
    st.caption(
        "The following packets are preserved with their original dates and claim ceilings. "
        "They are provenance, not the current organizer-window decision above."
    )
    packet_path = ROOT / "evidence" / "decision-packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    st.markdown("#### Pre-kickoff product decision")
    st.json(packet)
    readiness_packet_path = ROOT / "evidence" / "evaluation-readiness-decision.json"
    readiness_packet = json.loads(readiness_packet_path.read_text(encoding="utf-8"))
    st.markdown("#### Pre-kickoff evaluation-readiness decision")
    st.json(readiness_packet)
    normalization_packet_path = ROOT / "evidence" / "normalization-bridge-decision.json"
    normalization_packet = json.loads(normalization_packet_path.read_text(encoding="utf-8"))
    st.markdown("#### Alpaca normalization-bridge decision")
    st.json(normalization_packet)
    st.markdown(
        "<p class='small-note'>Claim ceiling: C1 after local verification. No profitability, safety, or deployment claim.</p>",
        unsafe_allow_html=True,
    )
