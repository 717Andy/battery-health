namespace BatteryHealth.Core.Domain;

public sealed class StressScenario
{
    public double AmbientTemperatureC { get; set; } = 24.0;
    public double DischargeCRate { get; set; } = 1.0;
    public int? CurrentCycle { get; set; }
    public double? EolCapacityFraction { get; set; }
}

public sealed class FadePoint
{
    public int CycleIndex { get; init; }
    public double CapacityAh { get; init; }
    public double Soh { get; init; }
}

public sealed class StressSimulation
{
    public double AccelerationFactor { get; init; }
    public double TemperatureAcceleration { get; init; }
    public double CRateAcceleration { get; init; }
    public double AmbientTemperatureC { get; init; }
    public double DischargeCRate { get; init; }
    public int CurrentCycle { get; init; }
    public double CurrentCapacityAh { get; init; }
    public double EolCapacityAh { get; init; }
    public double EolFraction { get; init; }
    public int BaselineEolCycle { get; init; }
    public int StressedEolCycle { get; init; }
    public int BaselineRulCycles { get; init; }
    public int StressedRulCycles { get; init; }
    public bool BaselineExtrapolated { get; init; }
    public bool StressedExtrapolated { get; init; }
    public IReadOnlyList<FadePoint> Baseline { get; init; } = [];
    public IReadOnlyList<FadePoint> Stressed { get; init; } = [];
}
