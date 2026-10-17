using System.Text.Json;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Parsing;
using BatteryHealth.Core.Services;
using BatteryHealth.Core.Simulation;

namespace BatteryHealth.Core.Tests;

public class DecisionExportTests
{
    [Fact]
    public void FadeRul_UsesNameplateForBothThresholds()
    {
        var battery = Sample();
        Assert.Equal(29, FadeRul.EstimateCycles(battery, 0.70, 1));
        Assert.Equal(19, FadeRul.EstimateCycles(battery, 0.80, 1));

        var atNameplate = FadeRul.EstimateCycles(battery, 0.80, 1);
        battery.RatedCapacityAh = 1.1;
        Assert.NotEqual(atNameplate, FadeRul.EstimateCycles(battery, 0.80, 1));
    }

    [Fact]
    public void DischargeAt_UsesTheExactCycleIndex()
    {
        var battery = Sample();
        Assert.Equal(20, battery.DischargeAt(20)!.CycleIndex);
        Assert.Null(battery.DischargeAt(15));
        Assert.Equal(20, battery.CycleAt(25)!.CycleIndex);
    }

    [Fact]
    public void JsonWithoutNameplate_MarksCapacityAssumed()
    {
        var record = CanonicalJsonParser.Parse("""
            {"batteryId":"X","cycles":[{"cycleIndex":1,"type":"discharge","capacityAh":1.5}]}
            """);
        Assert.True(record.RatedCapacityAssumed);
        Assert.Equal(2.0, record.RatedCapacityAh);
    }

    [Fact]
    public void JsonWithNameplate_IsNotAssumed()
    {
        var record = CanonicalJsonParser.Parse("""
            {"batteryId":"X","ratedCapacityAh":1.1,"cycles":[{"cycleIndex":1,"type":"discharge","capacityAh":1.0}]}
            """);
        Assert.False(record.RatedCapacityAssumed);
        Assert.Equal(1.1, record.RatedCapacityAh);
    }

    [Fact]
    public void CsvAndJson_IncludeBothRulLinesAndTheScenario()
    {
        var battery = Sample();
        var trajectory = new[]
        {
            new ForecastResult
            {
                BatteryId = "CELL",
                CycleIndex = 1,
                PredictedSoh = 0.95,
                ObservedSoh = 1.0,
                PredictedRulCycles = 40,
            },
        };
        var stress = DegradationSimulator.Simulate(battery, new StressScenario
        {
            AmbientTemperatureC = 45,
            DischargeCRate = 2,
            CurrentCycle = 1,
        });
        var report = DecisionReport.Create(battery, trajectory, stress, ProtocolError.TypicalMiss(12, 468), decisionCycle: 1);
        var csv = report.ToCsv();
        Assert.Contains("rul_to_70_cycles", csv);
        Assert.Contains("rul_to_70_fade_cycles", csv);
        Assert.Contains("rul_to_80_cycles", csv);
        Assert.Contains("selected", csv);
        Assert.Contains("acceleration_ea_0_30", csv);
        Assert.Contains("acceleration_ea_0_70", csv);

        using var exported = JsonDocument.Parse(report.ToJson());
        var row = exported.RootElement.GetProperty("rows")[0];
        Assert.Equal(19, row.GetProperty("rulTo80Cycles").GetDouble());
        Assert.Equal(40, row.GetProperty("rulTo70Cycles").GetDouble());
        Assert.Equal(29, row.GetProperty("rulTo70FadeCycles").GetDouble());
        Assert.True(row.GetProperty("selected").GetBoolean());
        var decision = exported.RootElement.GetProperty("decision");
        Assert.Equal(1, decision.GetProperty("cycle").GetInt32());
        Assert.Equal(29, decision.GetProperty("fadeRulTo70Cycles").GetDouble());
        Assert.Equal(19, decision.GetProperty("fadeRulTo80Cycles").GetDouble());
        Assert.Contains("empirical error", decision.GetProperty("typicalProtocolError").GetString());
        Assert.Contains("stressed_rul_to_70", csv);
        Assert.Contains("stressed_rul_to_80_ea_0_70", csv);
        Assert.Equal(report.StressedRulTo70, report.StressedRulTo70Ea050);
        Assert.Equal(report.StressedRulTo80, report.StressedRulTo80Ea050);
        Assert.True(report.StressedRulTo70 <= report.BaselineRulTo70);
        Assert.True(report.StressedRulTo70Ea070 <= report.StressedRulTo70Ea030);
        Assert.True(report.AccelerationAtEa070 > report.AccelerationAtEa050);
        Assert.True(report.AccelerationAtEa050 > report.AccelerationAtEa030);
        Assert.Equal(45, report.ScenarioAmbientC);
        Assert.True(report.AccelerationFactor > 1);
    }

    [Fact]
    public void OmittedDecisionCycle_SelectsTheLastTracedDischarge()
    {
        var battery = Sample();
        battery.Cycles.Add(new BatteryCycle
        {
            CycleIndex = 40,
            Type = "discharge",
            CapacityAh = 1.2,
            TimeS = [0, 10],
            VoltageV = [4.0, 3.2],
        });
        var trajectory = new[]
        {
            new ForecastResult { BatteryId = "CELL", CycleIndex = 1, PredictedSoh = 0.95, PredictedRulCycles = 40 },
            new ForecastResult { BatteryId = "CELL", CycleIndex = 40, PredictedSoh = 0.7, PredictedRulCycles = 5 },
        };
        var stress = DegradationSimulator.Simulate(battery, new StressScenario { AmbientTemperatureC = 24, DischargeCRate = 1 });
        var report = DecisionReport.Create(battery, trajectory, stress);
        Assert.Equal(40, report.DecisionCycle);
        Assert.Equal(40, report.Decision!.Cycle);
        Assert.False(report.Rows.First(row => row.CycleIndex == 1).Selected);
        Assert.True(report.Rows.First(row => row.CycleIndex == 40).Selected);
    }

    [Fact]
    public void FeatureShift_ComparesTheSelectedCycleWithTheFirst()
    {
        var baseline = new Dictionary<string, double>
        {
            ["energy_wh"] = 6,
            ["duration_s"] = 3000,
            ["time_to_3v0"] = 2500,
        };
        var current = new Dictionary<string, double>
        {
            ["energy_wh"] = 4.5,
            ["duration_s"] = 2400,
            ["time_to_3v0"] = 2000,
        };
        var text = FeatureShift.Describe(40, current, 1, baseline);
        Assert.Contains("energy_wh -25.0%", text);
        Assert.Contains("duration_s -20.0%", text);
        Assert.Contains("time_to_3v0 -20.0%", text);
        Assert.Contains("first scored discharge", FeatureShift.Describe(1, baseline, 1, baseline));
    }

    [Fact]
    public void ProtocolError_ReadsUncensoredNestedRmse()
    {
        var metrics = """
            {"rulNestedSoh":{"pooledExcludingCensored":{"rmse":11.97,"n":468}}}
            """;
        Assert.True(ProtocolError.TryRead(metrics, out var rmse, out var n));
        Assert.Equal(11.97, rmse);
        Assert.Equal(468, n);
        Assert.Contains("not a calibrated prediction interval", ProtocolError.TypicalMiss(rmse, n));
    }

    private static BatteryRecord Sample() => new()
    {
        BatteryId = "CELL",
        RatedCapacityAh = 2.0,
        Cycles =
        [
            new BatteryCycle { CycleIndex = 1, Type = "discharge", CapacityAh = 2.0, TimeS = [0, 1], VoltageV = [4, 3] },
            new BatteryCycle { CycleIndex = 10, Type = "discharge", CapacityAh = 1.7 },
            new BatteryCycle { CycleIndex = 20, Type = "discharge", CapacityAh = 1.5 },
            new BatteryCycle { CycleIndex = 30, Type = "discharge", CapacityAh = 1.3 },
        ],
    };
}
