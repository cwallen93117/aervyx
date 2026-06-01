export type ScoringHelpCopy = { title: string; body: string };

export const scoringFieldHelp = {
  scoring_formula: {
    title: "Scoring formula",
    body: "Chooses the GAP ruleset/version. Changing this will update the parameter checkboxes and numeric defaults below to match that version's standard settings. You can still override individual parameters after selecting a formula.",
  },
  nominal_goal_percent: {
    title: "Nominal goal",
    body: "The share of launched pilots expected to reach goal in a normal task. GAP uses it when computing validity and point allocation.",
  },
  score_back_time_minutes: {
    title: "Score-back time",
    body: "For a stopped task, flights are scored back from the stop time by this many minutes. CIVL guidance commonly uses 5 minutes for paragliding and 15 for hang gliding.",
  },
  goal_ss_penalty: {
    title: "Goal / SS penalty",
    body: "Stored as the speed-section penalty factor. It controls how much credit is kept when a ruleset applies a goal-versus-speed-section penalty.",
  },
  stopped_glide_bonus: {
    title: "Stopped-task glide bonus",
    body: "A stopped-task adjustment used when the chosen ruleset gives extra glide-related credit after a task stop.",
  },
  jump_the_gun_factor: {
    title: "Jump-the-gun factor",
    body: "The penalty rate for starting early. CIVL guidance describes jump-the-gun as a points-per-second early-start penalty.",
  },
  jump_the_gun_max_seconds: {
    title: "Jump-the-gun max",
    body: "The maximum early-start time scored or penalized under the jump-the-gun rule.",
  },
  use_distance_points: {
    title: "Distance points",
    body: "Turns the distance component on or off. When enabled, pilots earn points for the distance they fly along the task.",
  },
  use_time_points: {
    title: "Time points",
    body: "Turns the speed/time component on or off. When enabled, faster valid completions receive time points.",
  },
  use_leading_points: {
    title: "Leading points",
    body: "Enables the leading component. This rewards pilots for leading earlier on the course rather than only finishing fast.",
  },
  use_arrival_position_points: {
    title: "Arrival position points",
    body: "Enables arrival points based on finishing order at ESS or goal, depending on the scoring mode.",
  },
  use_arrival_time_points: {
    title: "Arrival time points",
    body: "Enables arrival points based on arrival time instead of only arrival order.",
  },
  use_departure_points: {
    title: "Departure points",
    body: "Enables the departure/start component. This is the GAP share sometimes called start or departure points.",
  },
  nominal_distance_km: {
    title: "Nominal distance",
    body: "The reference distance for a normal valid task. GAP compares actual task performance against this value when computing validity and weights.",
  },
  nominal_time_hours: {
    title: "Nominal time",
    body: "The reference winning time for a normal task. GAP compares the best task time against this value when computing time validity.",
  },
  nominal_launch: {
    title: "Nominal launch",
    body: "The expected share of registered pilots who launch in a normal task. GAP launch validity compares actual launches against this target.",
  },
  minimum_distance_km: {
    title: "Minimum distance",
    body: "The minimum scored distance floor. It defines the baseline before distance validity and distance-point scaling begin.",
  },
  penalties_text: {
    title: "Task penalty / notes JSON",
    body: "Repo-specific raw formula overrides or notes stored with the event. Use it for extra scoring-engine parameters that do not yet have dedicated fields.",
  },
  day_quality_override: {
    title: "Day quality override",
    body: "Forces a fixed day quality instead of using the value GAP would normally compute from task validity.",
  },
  time_points_if_not_in_goal: {
    title: "Time points if not in goal",
    body: "Controls whether and how time-related points are kept for pilots who do not make ESS or goal.",
  },
  min_time_span_for_valid_task_minutes: {
    title: "Min time span for valid task",
    body: "The minimum elapsed task span required before the task can be treated as valid under this scoring setup.",
  },
  leading_weight_factor: {
    title: "Leading weight factor",
    body: "Scales the size of the leading-points share relative to the other available point weights.",
  },
  turnpoint_radius_tolerance: {
    title: "Turnpoint radius tolerance",
    body: "Adds a small tolerance when cylinder crossings are checked so tiny GPS or geometry differences do not create false misses.",
  },
  turnpoint_radius_minimum_absolute_tolerance_m: {
    title: "Turnpoint minimum absolute tolerance",
    body: "A minimum meter-based floor for the turnpoint tolerance so very small cylinders still get a practical crossing tolerance.",
  },
  number_of_decimals_task_results: {
    title: "Task results decimals",
    body: "How many decimal places task-result scores are shown and rounded to.",
  },
  number_of_decimals_competition_results: {
    title: "Competition results decimals",
    body: "How many decimal places overall competition standings are shown and rounded to.",
  },
  scoring_altitude: {
    title: "Scoring altitude",
    body: "Chooses which altitude reference is used for altitude-sensitive scoring output and checks, such as GPS, QNH, or pressure altitude.",
  },
  final_glide_decelerator: {
    title: "Final glide decelerator",
    body: "Chooses the final-glide decelerator mode used near the end of the task when that rule is active.",
  },
  no_final_glide_decelerator_reason: {
    title: "No final glide decelerator reason",
    body: "A free-text note explaining why the final-glide decelerator is disabled or overridden for the event.",
  },
  use_1000_points_for_max_day_quality: {
    title: "Use 1000 points for max day quality",
    body: "Normalizes the maximum day to 1000 available points before other validity effects are applied.",
  },
  normalize_1000_before_day_quality: {
    title: "Normalize 1000 before day quality",
    body: "Forces the weight breakdown to normalize to 1000 points before day quality scales the task down.",
  },
  use_difficulty_for_distance_points: {
    title: "Use difficulty for distance points",
    body: "Uses GAP difficulty weighting for distance points instead of a simpler linear-only distance distribution.",
  },
  use_distance_squared_for_lc: {
    title: "Use distance squared for LC",
    body: "Uses squared distance inside the leading-coefficient calculation, increasing the influence of deeper course progress.",
  },
  use_semi_circle_control_zone_for_goal_line: {
    title: "Use semi-circle goal line control zone",
    body: "Treats the goal-line control zone as a semi-circle instead of the alternative control-zone interpretation.",
  },
  use_proportional_leading_weight_if_nobody_in_goal: {
    title: "Proportional leading weight if nobody in goal",
    body: "Scales leading weight proportionally when no pilot reaches goal, instead of keeping the full default leading share.",
  },
  redistribute_removed_time_points_as_distance_points: {
    title: "Redistribute removed time points",
    body: "Shifts the point share removed from time points into distance points so total available points stay balanced.",
  },
  use_best_score_for_ftv_validity: {
    title: "Use best score for FTV validity",
    body: "Uses a pilot's best-score set when applying Fixed Total Validity so competition scoring follows the FTV approach.",
  },
  use_constant_leading_weight: {
    title: "Use constant leading weight",
    body: "Keeps the leading-point weight fixed instead of letting it vary with the normal GAP weight allocation behavior.",
  },
  use_pwca2019_for_lc: {
    title: "Use PWCA 2019 for LC",
    body: "Applies the PWCA 2019 leading-coefficient method rather than the default leading setup.",
  },
  use_flat_decline_of_timepoints: {
    title: "Use flat decline of time points",
    body: "Uses a flatter decline curve when reducing time points, so they taper off more gently across the field.",
  },
} as const satisfies Record<string, ScoringHelpCopy>;

export type ScoringHelpId = keyof typeof scoringFieldHelp;

export function FieldHelp({
  helpId,
  activeHelpId,
  setActiveHelpId,
}: {
  helpId: ScoringHelpId;
  activeHelpId: ScoringHelpId | null;
  setActiveHelpId: (value: ScoringHelpId | null) => void;
}) {
  const copy = scoringFieldHelp[helpId];
  const isOpen = activeHelpId === helpId;
  const popoverId = `scoring-help-${helpId}`;

  return (
    <span className={`field-help${isOpen ? " is-open" : ""}`}>
      <button
        type="button"
        className="field-help-button"
        aria-label={`What does ${copy.title} mean?`}
        aria-expanded={isOpen}
        aria-controls={popoverId}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setActiveHelpId(isOpen ? null : helpId);
        }}
      >
        i
      </button>
      {isOpen ? (
        <span className="field-help-popover" id={popoverId} role="dialog" aria-label={copy.title}>
          <strong>{copy.title}</strong>
          <span>{copy.body}</span>
        </span>
      ) : null}
    </span>
  );
}

export function LabelWithHelp({
  label,
  helpId,
  activeHelpId,
  setActiveHelpId,
}: {
  label: string;
  helpId: ScoringHelpId;
  activeHelpId: ScoringHelpId | null;
  setActiveHelpId: (value: ScoringHelpId | null) => void;
}) {
  return (
    <span className="field-label-with-help">
      <span>{label}</span>
      <FieldHelp helpId={helpId} activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
    </span>
  );
}
