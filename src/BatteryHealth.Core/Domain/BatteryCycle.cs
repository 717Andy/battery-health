namespace BatteryHealth.Core.Domain;

public sealed class BatteryCycle
{
    public int CycleIndex { get; set; }
    public string Type { get; set; } = "discharge";
    public double? AmbientTemperatureC { get; set; }
    public double? CapacityAh { get; set; }
    public List<double> TimeS { get; set; } = [];
    public List<double> VoltageV { get; set; } = [];
    public List<double> CurrentA { get; set; } = [];
    public List<double> TemperatureC { get; set; } = [];
    public Dictionary<string, double>? Features { get; set; }

    public bool HasTrace => TimeS.Count > 1 && VoltageV.Count > 1;

    public double? ObservedSoh(double ratedCapacityAh) =>
        CapacityAh is { } cap && ratedCapacityAh > 0 ? cap / ratedCapacityAh : null;
}
