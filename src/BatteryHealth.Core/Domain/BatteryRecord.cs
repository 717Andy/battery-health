namespace BatteryHealth.Core.Domain;

public sealed class BatteryRecord
{
    public string BatteryId { get; set; } = "";
    public string Source { get; set; } = "";
    public double RatedCapacityAh { get; set; } = 2.0;
    public double EolCapacityFraction { get; set; } = 0.70;
    public string? Chemistry { get; set; }
    public double? AmbientTemperatureC { get; set; }
    public string? SourceFile { get; set; }
    public string? Notes { get; set; }
    public List<BatteryCycle> Cycles { get; set; } = [];

    public IEnumerable<BatteryCycle> DischargeCycles =>
        Cycles.Where(c => string.Equals(c.Type, "discharge", StringComparison.OrdinalIgnoreCase));

    public double EolCapacityAh => RatedCapacityAh * EolCapacityFraction;

    public BatteryCycle? CycleAt(int cycleIndex) =>
        DischargeCycles.LastOrDefault(c => c.CycleIndex <= cycleIndex)
        ?? DischargeCycles.FirstOrDefault();
}
