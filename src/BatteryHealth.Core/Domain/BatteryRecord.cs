using System.Text.Json.Serialization;

namespace BatteryHealth.Core.Domain;

public sealed class BatteryRecord
{
    /// <summary>Nameplate the shipped SoH/RUL models were trained against.</summary>
    public const double TrainingRatedCapacityAh = 2.0;

    public string BatteryId { get; set; } = "";
    public string Source { get; set; } = "";
    public double RatedCapacityAh { get; set; } = 2.0;

    /// <summary>True when the file did not carry a nameplate and the parser supplied one.</summary>
    [JsonIgnore]
    public bool RatedCapacityAssumed { get; set; }
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

    public BatteryCycle? DischargeAt(int cycleIndex) =>
        DischargeCycles.FirstOrDefault(c => c.CycleIndex == cycleIndex);
}
