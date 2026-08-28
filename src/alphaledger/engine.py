from __future__ import annotations

from .brokers import Broker, SimulationBroker, abstention_receipt
from .critic import SkepticalCritic
from .ledger import EvidenceLedger
from .models import AccountState, GovernedCycleResult, MarketSnapshot, RiskPolicy
from .risk import DeterministicRiskGate
from .strategy import BoundedMomentumProposer


class GovernedTradingEngine:
    """Observe -> propose -> criticize -> gate -> execute/abstain -> receipt."""

    def __init__(
        self,
        *,
        proposer: BoundedMomentumProposer | None = None,
        critic: SkepticalCritic | None = None,
        risk_gate: DeterministicRiskGate | None = None,
        broker: Broker | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.proposer = proposer or BoundedMomentumProposer()
        self.critic = critic or SkepticalCritic()
        self.risk_gate = risk_gate or DeterministicRiskGate()
        self.broker = broker or SimulationBroker()
        self.ledger = ledger or EvidenceLedger()

    def run_cycle(
        self,
        snapshot: MarketSnapshot,
        account: AccountState,
        policy: RiskPolicy | None = None,
    ) -> GovernedCycleResult:
        frozen_policy = policy or RiskPolicy()
        thesis = self.proposer.propose(snapshot, account)
        critic = self.critic.review(thesis, snapshot)
        risk = self.risk_gate.evaluate(thesis, snapshot, account, frozen_policy, critic)
        receipt = self.broker.execute(thesis, snapshot) if risk.approved else abstention_receipt(thesis, risk.reasons)

        payload = {
            "snapshot": snapshot.to_dict(),
            "account": account.to_dict(),
            "policy": frozen_policy.to_dict(),
            "thesis": thesis.to_dict(),
            "critic": critic.to_dict(),
            "risk": risk.to_dict(),
            "receipt": receipt.to_dict(),
        }
        entry = self.ledger.append("governed_cycle", payload)
        return GovernedCycleResult(
            snapshot=snapshot,
            thesis=thesis,
            critic=critic,
            risk=risk,
            receipt=receipt,
            ledger_hash=entry["entry_hash"],
        )
