using BatteryHealth.Core.Domain;

namespace BatteryHealth.Core.Tests;

public class IntakeReportTests
{
    [Fact]
    public void FullDischarges_StateCountsAndBothEndOfLifeLines()
    {
        var report = IntakeReport.From(Cell(assumed: false, voltages: [[4.2, 2.8], [4.1, 2.9]]));
        Assert.Equal(2, report.DischargeCount);
        Assert.Equal(2, report.WithCapacity);
        Assert.Equal(2, report.WithTrace);
        Assert.False(report.NameplateAssumed);
        Assert.Equal(1.40, report.Eol70Ah, 2);
        Assert.Equal(1.60, report.Eol80Ah, 2);
        Assert.False(report.PartialDischarges);
        Assert.Contains(report.Lines, line => line.Contains("Nameplate 2.00 Ah was in the file."));
        Assert.Contains(report.Lines, line => line.Contains("70% (1.40 Ah)") && line.Contains("80% (1.60 Ah)"));
        Assert.DoesNotContain(report.Lines, line => line == IntakeReport.PartialNote);
    }

    [Fact]
    public void FewerThanHalfReachingThreeVolts_ArePartial()
    {
        var report = IntakeReport.From(Cell(assumed: true, voltages: [[4.2, 3.6], [4.2, 3.5], [4.2, 2.7]]));
        Assert.True(report.PartialDischarges);
        Assert.Contains(IntakeReport.PartialNote, report.Lines);
        Assert.Contains(report.Lines, line => line.Contains("assumed until you set it"));
    }

    [Fact]
    public void HalfReachingThreeVolts_IsNotPartial()
    {
        var report = IntakeReport.From(Cell(assumed: false, voltages: [[4.2, 3.4], [4.2, 2.9]]));
        Assert.False(report.PartialDischarges);
    }

    [Fact]
    public void NameplateChange_MovesAmpHourLinesAndLeavesThePartialNote()
    {
        var battery = Cell(assumed: true, voltages: [[4.2, 3.6], [4.2, 3.5]]);
        var before = IntakeReport.From(battery);
        battery.RatedCapacityAh = 1.1;
        battery.RatedCapacityAssumed = false;
        var after = IntakeReport.From(battery);
        Assert.Equal(0.77, after.Eol70Ah, 2);
        Assert.Equal(0.88, after.Eol80Ah, 2);
        Assert.NotEqual(before.Eol70Ah, after.Eol70Ah);
        Assert.Equal(before.PartialDischarges, after.PartialDischarges);
        Assert.True(after.PartialDischarges);
    }

    private static BatteryRecord Cell(bool assumed, double[][] voltages) => new()
    {
        BatteryId = "CELL",
        Source = "nasa",
        RatedCapacityAh = 2.0,
        RatedCapacityAssumed = assumed,
        Cycles = voltages.Select((voltage, index) => new BatteryCycle
        {
            CycleIndex = index + 1,
            Type = "discharge",
            CapacityAh = 1.8 - (0.1 * index),
            TimeS = Enumerable.Range(0, voltage.Length).Select(i => (double)i).ToList(),
            VoltageV = voltage.ToList(),
        }).ToList(),
    };
}
