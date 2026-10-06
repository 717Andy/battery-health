using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Simulation;

namespace BatteryHealth.Core.Tests;

public class SimulatorTests
{
    [Fact]
    public void Acceleration_IsUnityAtNasaReference()
    {
        Assert.Equal(1.0, DegradationSimulator.TemperatureAcceleration(24.0), 9);
        Assert.Equal(1.0, DegradationSimulator.CRateAcceleration(1.0), 9);
        Assert.Equal(1.0, DegradationSimulator.CombinedAcceleration(24.0, 1.0), 9);
    }

    [Fact]
    public void HotterAndFaster_IncreasesAcceleration()
    {
        Assert.True(DegradationSimulator.TemperatureAcceleration(45) > DegradationSimulator.TemperatureAcceleration(24));
        Assert.True(DegradationSimulator.CombinedAcceleration(45, 2) > DegradationSimulator.CombinedAcceleration(24, 1));
    }

    [Fact]
    public void Stress_ShortensRul()
    {
        var battery = Toy();
        var sim = DegradationSimulator.Simulate(battery, new StressScenario
        {
            AmbientTemperatureC = 45,
            DischargeCRate = 2,
            CurrentCycle = 5,
        });
        Assert.True(sim.AccelerationFactor > 1);
        Assert.True(sim.StressedRulCycles <= sim.BaselineRulCycles);
        Assert.True(sim.Stressed[^1].CapacityAh <= sim.Baseline[^1].CapacityAh);
    }

    private static BatteryRecord Toy()
    {
        var record = new BatteryRecord
        {
            BatteryId = "TOY",
            RatedCapacityAh = 2.0,
            EolCapacityFraction = 0.70,
        };
        for (var i = 1; i <= 20; i++)
        {
            record.Cycles.Add(new BatteryCycle
            {
                CycleIndex = i,
                Type = "discharge",
                CapacityAh = 2.0 - 0.04 * (i - 1),
            });
        }

        return record;
    }
}
