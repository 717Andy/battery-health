using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Simulation;

namespace BatteryHealth.Core.Tests;

public class StressOutlookTests
{
    [Fact]
    public void DefaultEa_MatchesTheReferenceCurve()
    {
        var battery = Cell();
        var implied = DegradationSimulator.Simulate(battery, new StressScenario
        {
            AmbientTemperatureC = 45,
            DischargeCRate = 2,
            CurrentCycle = 1,
            EolCapacityFraction = 0.70,
        });
        var explicitEa = DegradationSimulator.Simulate(battery, new StressScenario
        {
            AmbientTemperatureC = 45,
            DischargeCRate = 2,
            CurrentCycle = 1,
            EolCapacityFraction = 0.70,
            ArrheniusEaEv = 0.50,
        });
        Assert.Equal(implied.StressedRulCycles, explicitEa.StressedRulCycles);
        Assert.Equal(implied.AccelerationFactor, explicitEa.AccelerationFactor, 6);
    }

    [Fact]
    public void Outlook_ReportsBothThresholdsAndAShorterLifeWhenHotter()
    {
        var outlook = StressOutlook.From(Cell(), 45, 2, 1);
        Assert.Equal(1, outlook.StartCycle);
        Assert.True(outlook.StressedTo70 < outlook.BaselineTo70);
        Assert.True(outlook.StressedTo80 < outlook.BaselineTo80);
        Assert.Equal(outlook.StressedTo70, outlook.StressedTo70Ea050);
        Assert.Equal(outlook.StressedTo80, outlook.StressedTo80Ea050);
        Assert.True(outlook.StressedTo70Ea070 <= outlook.StressedTo70Ea030);
        Assert.True(outlook.StressedTo80Ea070 <= outlook.StressedTo80Ea030);
    }

    private static BatteryRecord Cell() => new()
    {
        BatteryId = "CELL",
        RatedCapacityAh = 2.0,
        Cycles =
        [
            new BatteryCycle { CycleIndex = 1, Type = "discharge", CapacityAh = 2.0 },
            new BatteryCycle { CycleIndex = 10, Type = "discharge", CapacityAh = 1.7 },
            new BatteryCycle { CycleIndex = 20, Type = "discharge", CapacityAh = 1.5 },
            new BatteryCycle { CycleIndex = 30, Type = "discharge", CapacityAh = 1.3 },
        ],
    };
}
