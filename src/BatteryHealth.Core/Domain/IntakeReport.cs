namespace BatteryHealth.Core.Domain;

/// <summary>
/// What a user checks before treating a forecast as a result:
/// the file can be scored, the nameplate is known, and the two end-of-life lines.
/// </summary>
public sealed class IntakeReport
{
    public const string StartingHint =
        "Three ways to start. Processed NASA JSON opens directly. " +
        "CALCE CSV or Excel opens directly; type the nameplate beside the cycle list. " +
        "A NASA .mat file has to be converted first with python -m batteryhealth.download, " +
        "or POST it to the sidecar /parse/nasa, then open the processed JSON.";

    public const string PartialNote =
        "These discharges look partial relative to the NASA protocol the model was trained on.";

    public string Source { get; init; } = "";
    public int DischargeCount { get; init; }
    public int WithCapacity { get; init; }
    public int WithTrace { get; init; }
    public bool NameplateAssumed { get; init; }
    public double NameplateAh { get; init; }
    public double Eol70Ah { get; init; }
    public double Eol80Ah { get; init; }
    public bool PartialDischarges { get; init; }

    public IReadOnlyList<string> Lines { get; init; } = [];

    public static IntakeReport From(BatteryRecord battery)
    {
        var discharges = battery.DischargeCycles.ToList();
        var traced = discharges.Where(cycle => cycle.HasTrace).ToList();
        var reached = traced.Count(ReachesThreeVolts);
        var partial = traced.Count > 0 && reached < traced.Count / 2.0;
        var nameplate = battery.RatedCapacityAh;
        var lines = new List<string>
        {
            $"Source {SourceLabel(battery)}. {discharges.Count} discharge cycles, " +
            $"{discharges.Count(cycle => cycle.CapacityAh.HasValue)} with capacity, {traced.Count} with a sensor trace.",
            battery.RatedCapacityAssumed
                ? $"Nameplate {nameplate:0.00} Ah was not in the file and is assumed until you set it."
                : $"Nameplate {nameplate:0.00} Ah was in the file.",
            $"Lab stop is 70% ({nameplate * 0.70:0.00} Ah). Warranty line is 80% ({nameplate * 0.80:0.00} Ah).",
        };
        if (partial)
        {
            lines.Add(PartialNote);
        }

        return new IntakeReport
        {
            Source = SourceLabel(battery),
            DischargeCount = discharges.Count,
            WithCapacity = discharges.Count(cycle => cycle.CapacityAh.HasValue),
            WithTrace = traced.Count,
            NameplateAssumed = battery.RatedCapacityAssumed,
            NameplateAh = nameplate,
            Eol70Ah = nameplate * 0.70,
            Eol80Ah = nameplate * 0.80,
            PartialDischarges = partial,
            Lines = lines,
        };
    }

    private static bool ReachesThreeVolts(BatteryCycle cycle) =>
        cycle.VoltageV.Count > 0 && cycle.VoltageV.Min() <= 3.0;

    private static string SourceLabel(BatteryRecord battery) =>
        string.IsNullOrWhiteSpace(battery.Source) ? "unknown" : battery.Source;
}
