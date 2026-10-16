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
        var report = DecisionReport.Create(battery, trajectory, stress, ProtocolError.TypicalMiss(12, 468));
        var csv = report.ToCsv();
        Assert.Contains("rul_to_70_cycles", csv);
        Assert.Contains("rul_to_80_cycles", csv);
        Assert.Contains("scenario_temperature_c", csv);
        Assert.Contains("acceleration_factor", csv);
        Assert.Contains("19", csv);

        using var exported = JsonDocument.Parse(report.ToJson());
        var row = exported.RootElement.GetProperty("rows")[0];
        Assert.Equal(19, row.GetProperty("rulTo80Cycles").GetDouble());
        Assert.Equal(40, row.GetProperty("rulTo70Cycles").GetDouble());
        Assert.Contains("empirical error", exported.RootElement.GetProperty("typicalProtocolError").GetString());
        Assert.Equal(45, report.ScenarioAmbientC);
        Assert.True(report.AccelerationFactor > 1);
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
