using BatteryHealth.Core.Domain;

namespace BatteryHealth.Core.Simulation;

/// <summary>
/// Cycles remaining to 70% and 80% of the nameplate, at the reference Ea and across the review band.
/// The fade curve itself stays the 0.50 eV scenario.
/// </summary>
public sealed class StressOutlook
{
    public int StartCycle { get; init; }
    public int BaselineTo70 { get; init; }
    public int StressedTo70 { get; init; }
    public int BaselineTo80 { get; init; }
    public int StressedTo80 { get; init; }
    public int StressedTo70Ea030 { get; init; }
    public int StressedTo70Ea050 { get; init; }
    public int StressedTo70Ea070 { get; init; }
    public int StressedTo80Ea030 { get; init; }
    public int StressedTo80Ea050 { get; init; }
    public int StressedTo80Ea070 { get; init; }
    public bool StressedExtrapolated { get; init; }
    public IReadOnlyList<FadePoint> StressedCurve { get; init; } = [];

    public static StressOutlook From(BatteryRecord battery, double ambientC, double cRate, int? currentCycle)
    {
        var reference = Run(battery, ambientC, cRate, currentCycle, 0.70, DegradationSimulator.ArrheniusEaEv);
        var to80 = Run(battery, ambientC, cRate, currentCycle, 0.80, DegradationSimulator.ArrheniusEaEv);
        return new StressOutlook
        {
            StartCycle = reference.CurrentCycle,
            BaselineTo70 = reference.BaselineRulCycles,
            StressedTo70 = reference.StressedRulCycles,
            BaselineTo80 = to80.BaselineRulCycles,
            StressedTo80 = to80.StressedRulCycles,
            StressedTo70Ea030 = Run(battery, ambientC, cRate, currentCycle, 0.70, 0.30).StressedRulCycles,
            StressedTo70Ea050 = reference.StressedRulCycles,
            StressedTo70Ea070 = Run(battery, ambientC, cRate, currentCycle, 0.70, 0.70).StressedRulCycles,
            StressedTo80Ea030 = Run(battery, ambientC, cRate, currentCycle, 0.80, 0.30).StressedRulCycles,
            StressedTo80Ea050 = to80.StressedRulCycles,
            StressedTo80Ea070 = Run(battery, ambientC, cRate, currentCycle, 0.80, 0.70).StressedRulCycles,
            StressedExtrapolated = reference.StressedExtrapolated || to80.StressedExtrapolated,
            StressedCurve = reference.Stressed,
        };
    }

    private static StressSimulation Run(BatteryRecord battery, double ambientC, double cRate, int? currentCycle, double fraction, double ea) =>
        DegradationSimulator.Simulate(battery, new StressScenario
        {
            AmbientTemperatureC = ambientC,
            DischargeCRate = cRate,
            CurrentCycle = currentCycle,
            EolCapacityFraction = fraction,
            ArrheniusEaEv = ea,
        });
}
