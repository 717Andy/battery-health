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
    public double RulTo70FadeCycles { get; init; }
    public double RulTo80Cycles { get; init; }
    public bool HasTrace { get; init; }
    public bool Selected { get; init; }
}

public sealed class DecisionSummary
{
    public string BatteryId { get; init; } = "";
    public int Cycle { get; init; }
    public double NameplateAh { get; init; }
    public double PredictedSoh { get; init; }
    public double ModelRulTo70Cycles { get; init; }
    public double FadeRulTo70Cycles { get; init; }
    public double FadeRulTo80Cycles { get; init; }
    public string? TypicalProtocolError { get; init; }
    public double ScenarioAmbientC { get; init; }
    public double ScenarioCRate { get; init; }
    public double AccelerationFactor { get; init; }
    public double AccelerationAtEa030 { get; init; }
    public double AccelerationAtEa050 { get; init; }
    public double AccelerationAtEa070 { get; init; }
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
    public double AccelerationAtEa030 { get; init; }
    public double AccelerationAtEa050 { get; init; }
    public double AccelerationAtEa070 { get; init; }
    public string ScenarioClaim { get; init; } = DegradationSimulator.ScenarioClaim;
    public int? DecisionCycle { get; init; }
    public DecisionSummary? Decision { get; init; }
    public IReadOnlyList<DecisionRow> Rows { get; init; } = [];

    public static DecisionReport Create(
        BatteryRecord battery,
        IReadOnlyList<ForecastResult> trajectory,
        StressSimulation stress,
        string? typicalProtocolError = null,
        int? decisionCycle = null)
    {
        var byCycle = battery.DischargeCycles.ToDictionary(c => c.CycleIndex);
        var drafted = new List<DecisionRow>(trajectory.Count);
        foreach (var forecast in trajectory)
        {
            byCycle.TryGetValue(forecast.CycleIndex, out var cycle);
            drafted.Add(new DecisionRow
            {
                CycleIndex = forecast.CycleIndex,
                MeasuredCapacityAh = cycle?.CapacityAh,
                PredictedSoh = forecast.PredictedSoh,
                MeasuredSoh = forecast.ObservedSoh,
                RulTo70Cycles = forecast.PredictedRulCycles,
                RulTo70FadeCycles = FadeRul.EstimateCycles(battery, 0.70, forecast.CycleIndex),
                RulTo80Cycles = FadeRul.EstimateCycles(battery, 0.80, forecast.CycleIndex),
                HasTrace = cycle?.HasTrace ?? false,
            });
        }

        var selected = ResolveDecisionCycle(battery, drafted, decisionCycle);
        var rows = drafted.Select(row => new DecisionRow
        {
            CycleIndex = row.CycleIndex,
            MeasuredCapacityAh = row.MeasuredCapacityAh,
            PredictedSoh = row.PredictedSoh,
            MeasuredSoh = row.MeasuredSoh,
            RulTo70Cycles = row.RulTo70Cycles,
            RulTo70FadeCycles = row.RulTo70FadeCycles,
            RulTo80Cycles = row.RulTo80Cycles,
            HasTrace = row.HasTrace,
            Selected = selected is { } cycle && row.CycleIndex == cycle,
        }).ToList();

        var ea030 = DegradationSimulator.ScenarioAcceleration(stress.AmbientTemperatureC, stress.DischargeCRate, 0.30);
        var ea050 = DegradationSimulator.ScenarioAcceleration(stress.AmbientTemperatureC, stress.DischargeCRate, 0.50);
        var ea070 = DegradationSimulator.ScenarioAcceleration(stress.AmbientTemperatureC, stress.DischargeCRate, 0.70);
        DecisionSummary? decision = null;
        if (selected is { } chosen && rows.FirstOrDefault(row => row.CycleIndex == chosen) is { } chosenRow)
        {
            decision = new DecisionSummary
            {
                BatteryId = battery.BatteryId,
                Cycle = chosen,
                NameplateAh = battery.RatedCapacityAh,
                PredictedSoh = chosenRow.PredictedSoh,
                ModelRulTo70Cycles = chosenRow.RulTo70Cycles,
                FadeRulTo70Cycles = chosenRow.RulTo70FadeCycles,
                FadeRulTo80Cycles = chosenRow.RulTo80Cycles,
                TypicalProtocolError = typicalProtocolError,
                ScenarioAmbientC = stress.AmbientTemperatureC,
                ScenarioCRate = stress.DischargeCRate,
                AccelerationFactor = stress.AccelerationFactor,
                AccelerationAtEa030 = ea030,
                AccelerationAtEa050 = ea050,
                AccelerationAtEa070 = ea070,
            };
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
            AccelerationAtEa030 = ea030,
            AccelerationAtEa050 = ea050,
            AccelerationAtEa070 = ea070,
            DecisionCycle = selected,
            Decision = decision,
            Rows = rows,
        };
    }

    private static int? ResolveDecisionCycle(BatteryRecord battery, IReadOnlyList<DecisionRow> rows, int? requested)
    {
        if (requested is { } cycle)
        {
            return rows.Any(row => row.CycleIndex == cycle)
                ? cycle
                : throw new InvalidOperationException($"No discharge cycle {cycle}.");
        }

        var traced = battery.DischargeCycles.LastOrDefault(cycle => cycle.HasTrace);
        if (traced is not null && rows.Any(row => row.CycleIndex == traced.CycleIndex))
        {
            return traced.CycleIndex;
        }

        return rows.Count == 0 ? null : rows[^1].CycleIndex;
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
        builder.AppendLine("cycle_index,measured_capacity_ah,predicted_soh,measured_soh,rul_to_70_cycles,rul_to_70_fade_cycles,rul_to_80_cycles,has_trace,selected,scenario_temperature_c,scenario_c_rate,acceleration_factor,acceleration_ea_0_30,acceleration_ea_0_50,acceleration_ea_0_70");
        foreach (var row in Rows)
        {
            builder.Append(row.CycleIndex.ToString(culture)).Append(',')
                .Append(Format(row.MeasuredCapacityAh)).Append(',')
                .Append(row.PredictedSoh.ToString("G9", culture)).Append(',')
                .Append(Format(row.MeasuredSoh)).Append(',')
                .Append(row.RulTo70Cycles.ToString("G9", culture)).Append(',')
                .Append(row.RulTo70FadeCycles.ToString("G9", culture)).Append(',')
                .Append(row.RulTo80Cycles.ToString("G9", culture)).Append(',')
                .Append(row.HasTrace ? "true" : "false").Append(',')
                .Append(row.Selected ? "true" : "false").Append(',')
                .Append(ScenarioAmbientC.ToString("G9", culture)).Append(',')
                .Append(ScenarioCRate.ToString("G9", culture)).Append(',')
                .Append(AccelerationFactor.ToString("G9", culture)).Append(',')
                .Append(AccelerationAtEa030.ToString("G9", culture)).Append(',')
                .Append(AccelerationAtEa050.ToString("G9", culture)).Append(',')
                .Append(AccelerationAtEa070.ToString("G9", culture))
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
