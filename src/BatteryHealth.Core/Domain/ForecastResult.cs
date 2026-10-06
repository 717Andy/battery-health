namespace BatteryHealth.Core.Domain;

public sealed class ForecastResult
{
    public required string BatteryId { get; init; }
    public int CycleIndex { get; init; }
    public double PredictedSoh { get; init; }
    public double PredictedSohPercent => PredictedSoh * 100.0;
    public double? ObservedSoh { get; init; }
    public double PredictedRulCycles { get; init; }
    public double EolCapacityFraction { get; init; }
    public double EolCapacityAh { get; init; }
    public string EolDefinition { get; init; } =
        "Cycles remaining until discharge capacity reaches 70% of rated (NASA PCoE: 2.0 Ah → 1.4 Ah).";
    public IReadOnlyDictionary<string, double> Features { get; init; } = new Dictionary<string, double>();
}
