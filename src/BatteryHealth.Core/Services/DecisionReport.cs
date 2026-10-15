using System.Globalization;
using System.Text;
using System.Text.Json;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Simulation;

namespace BatteryHealth.Core.Services;

public sealed class DecisionRow
{
    public int CycleIndex { get; init; }
    public double? MeasuredCapacityAh { get; init; }
    public double PredictedSoh { get; init; }
    public double? MeasuredSoh { get; init; }
    public double RulTo70Cycles { get; init; }
    public double RulTo80Cycles { get; init; }
    public bool HasTrace { get; init; }
}

public sealed class DecisionReport
{
    public string BatteryId { get; init; } = "";
    public double RatedCapacityAh { get; init; }
    public bool RatedCapacityAssumed { get; init; }
    public string Applicability { get; init; } = ProtocolError.Applicability;
    public string? TypicalProtocolError { get; init; }
    public double ScenarioAmbientC { get; init; }
    public double ScenarioCRate { get; init; }
    public double AccelerationFactor { get; init; }
    public string ScenarioClaim { get; init; } = DegradationSimulator.ScenarioClaim;
    public IReadOnlyList<DecisionRow> Rows { get; init; } = [];

    public static DecisionReport Create(
        BatteryRecord battery,
        IReadOnlyList<ForecastResult> trajectory,
        StressSimulation stress,
        string? typicalProtocolError = null)
    {
        var byCycle = battery.DischargeCycles.ToDictionary(c => c.CycleIndex);
        var rows = new List<DecisionRow>(trajectory.Count);
        foreach (var forecast in trajectory)
        {
            byCycle.TryGetValue(forecast.CycleIndex, out var cycle);
            rows.Add(new DecisionRow
            {
                CycleIndex = forecast.CycleIndex,
                MeasuredCapacityAh = cycle?.CapacityAh,
                PredictedSoh = forecast.PredictedSoh,
                MeasuredSoh = forecast.ObservedSoh,
                RulTo70Cycles = forecast.PredictedRulCycles,
                RulTo80Cycles = FadeRul.EstimateCycles(battery, 0.80, forecast.CycleIndex),
                HasTrace = cycle?.HasTrace ?? false,
            });
        }

        return new DecisionReport
        {
            BatteryId = battery.BatteryId,
            RatedCapacityAh = battery.RatedCapacityAh,
            RatedCapacityAssumed = battery.RatedCapacityAssumed,
            TypicalProtocolError = typicalProtocolError,
            ScenarioAmbientC = stress.AmbientTemperatureC,
            ScenarioCRate = stress.DischargeCRate,
            AccelerationFactor = stress.AccelerationFactor,
            Rows = rows,
        };
    }

    public string ToJson() =>
        JsonSerializer.Serialize(this, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });

    public string ToCsv()
    {
        var culture = CultureInfo.InvariantCulture;
        var builder = new StringBuilder();
        builder.AppendLine("cycle_index,measured_capacity_ah,predicted_soh,measured_soh,rul_to_70_cycles,rul_to_80_cycles,has_trace,scenario_temperature_c,scenario_c_rate,acceleration_factor");
        foreach (var row in Rows)
        {
            builder.Append(row.CycleIndex.ToString(culture)).Append(',')
                .Append(Format(row.MeasuredCapacityAh)).Append(',')
                .Append(row.PredictedSoh.ToString("G9", culture)).Append(',')
                .Append(Format(row.MeasuredSoh)).Append(',')
                .Append(row.RulTo70Cycles.ToString("G9", culture)).Append(',')
                .Append(row.RulTo80Cycles.ToString("G9", culture)).Append(',')
                .Append(row.HasTrace ? "true" : "false").Append(',')
                .Append(ScenarioAmbientC.ToString("G9", culture)).Append(',')
                .Append(ScenarioCRate.ToString("G9", culture)).Append(',')
                .Append(AccelerationFactor.ToString("G9", culture))
                .AppendLine();
        }

        return builder.ToString();
    }

    public static void WritePair(string path, DecisionReport report)
    {
        var csvPath = Path.ChangeExtension(path, ".csv");
        var jsonPath = Path.ChangeExtension(path, ".json");
        File.WriteAllText(csvPath, report.ToCsv());
        File.WriteAllText(jsonPath, report.ToJson());
    }

    private static string Format(double? value) =>
        value is { } number ? number.ToString("G9", CultureInfo.InvariantCulture) : "";
}
