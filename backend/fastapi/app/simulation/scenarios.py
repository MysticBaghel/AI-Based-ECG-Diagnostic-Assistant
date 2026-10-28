"""The built-in simulator's scenario library.

Each scenario is a *teaching signal*, not a patient: a parameterised PQRST beat
timeline plus the scalar values a wearable would report alongside it. The
dashboard lets an operator pick one, and the recording that results is
indistinguishable, on the wire, from the same device streaming real data -
which is the point, because the analysis, the report and the WebSocket path all
have to be exercised exactly as they would be in the field.

The labels name the rhythm the generator is producing. They are **ground truth
for the simulation**, not a classification: nothing here diagnoses anything,
and the analysis pipeline receives the samples only.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (offset from the R wave in seconds, Gaussian width in seconds, amplitude in mV)
Wave = tuple[float, float, float]

#: A premature ventricular contraction: wide, tall and bizarre, with a
#: discordant T wave and no P wave - the shape a VPB has on a single lead.
PVC_WAVES: tuple[Wave, ...] = (
    (0.000, 0.045, 1.35),
    (0.055, 0.030, -0.55),
    (0.260, 0.055, -0.35),
)


@dataclass(frozen=True)
class Scenario:
    """One simulated rhythm and the vitals that go with it."""

    key: str
    label: str
    description: str

    #: nominal rate, beats per minute (the irregular rhythm samples around it)
    heart_rate_bpm: float
    #: beat-to-beat jitter, as a fraction of the mean RR interval
    rr_variability: float = 0.03
    #: when set, RR is drawn uniformly from this (low, high) range in seconds
    irregular_rr: tuple[float, float] | None = None
    #: P-wave amplitude in mV; 0 removes the P wave entirely
    p_wave_mv: float = 0.10
    qrs_mv: float = 1.00
    t_wave_mv: float = 0.28
    #: fibrillatory baseline amplitude in mV (atrial fibrillation only)
    fibrillation_mv: float = 0.0
    #: insert a wide-complex beat every N beats
    pvc_every: int | None = None

    temperature_c: float = 36.8
    spo2_percent: float = 97.0
    motion_au: float = 0.4

    def waves(self, *, pvc: bool) -> tuple[Wave, ...]:
        """The beat morphology for this scenario."""
        if pvc:
            return PVC_WAVES

        waves: list[Wave] = []
        if self.p_wave_mv:
            waves.append((-0.160, 0.022, self.p_wave_mv))
        waves.extend(
            (
                (-0.018, 0.008, -0.12),
                (0.000, 0.010, self.qrs_mv),
                (0.026, 0.010, -0.22),
                (0.200, 0.042, self.t_wave_mv),
            )
        )
        return tuple(waves)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "heart_rate_bpm": self.heart_rate_bpm,
        }


SCENARIOS: dict[str, Scenario] = {
    "normal_sinus": Scenario(
        key="normal_sinus",
        label="Normal sinus rhythm",
        description=(
            "Regular 72 bpm with a visible P wave. The control recording: a "
            "healthy trace for comparison."
        ),
        heart_rate_bpm=72.0,
        temperature_c=36.8,
        spo2_percent=97.4,
        motion_au=0.5,
    ),
    "sinus_bradycardia": Scenario(
        key="sinus_bradycardia",
        label="Sinus bradycardia",
        description=(
            "A slow but regular rhythm around 46 bpm. A low resting rate is "
            "common in athletes and in some medications."
        ),
        heart_rate_bpm=46.0,
        rr_variability=0.02,
        t_wave_mv=0.30,
        temperature_c=36.5,
        spo2_percent=97.0,
        motion_au=0.2,
    ),
    "sinus_tachycardia": Scenario(
        key="sinus_tachycardia",
        label="Sinus tachycardia",
        description=(
            "A fast regular rhythm around 128 bpm. Exercise, fever and stress "
            "all produce it; the P wave is still present."
        ),
        heart_rate_bpm=128.0,
        rr_variability=0.02,
        p_wave_mv=0.12,
        t_wave_mv=0.22,
        temperature_c=37.4,
        spo2_percent=96.2,
        motion_au=0.8,
    ),
    "atrial_fibrillation": Scenario(
        key="atrial_fibrillation",
        label="Atrial fibrillation",
        description=(
            "Irregularly irregular RR intervals with no P wave and a fine "
            "fibrillatory baseline - the trace a single lead shows in AF."
        ),
        heart_rate_bpm=96.0,
        irregular_rr=(0.38, 0.92),
        p_wave_mv=0.0,
        qrs_mv=0.95,
        t_wave_mv=0.18,
        fibrillation_mv=0.06,
        temperature_c=36.9,
        spo2_percent=95.4,
        motion_au=0.6,
    ),
    "frequent_pvc": Scenario(
        key="frequent_pvc",
        label="Frequent PVCs",
        description=(
            "Every third beat is a wide, premature ventricular complex with a "
            "compensatory pause - an ectopic rhythm on an otherwise sinus trace."
        ),
        heart_rate_bpm=74.0,
        rr_variability=0.02,
        pvc_every=3,
        temperature_c=36.7,
        spo2_percent=96.6,
        motion_au=0.4,
    ),
}

DEFAULT_SCENARIO = "normal_sinus"


def get_scenario(key: str) -> Scenario:
    """Look a scenario up, with a message that lists the alternatives."""
    try:
        return SCENARIOS[key]
    except KeyError as exc:
        raise KeyError(
            f"unknown scenario {key!r}; expected one of {sorted(SCENARIOS)}"
        ) from exc
