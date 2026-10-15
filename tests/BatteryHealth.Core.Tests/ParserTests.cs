using BatteryHealth.Core.Parsing;

namespace BatteryHealth.Core.Tests;

public class ParserTests
{
    private static string Fixture(string name) =>
        Path.Combine(AppContext.BaseDirectory, "fixtures", name);

    [Fact]
    public void CanonicalJson_ReadsTinyBattery()
    {
        var record = CanonicalJsonParser.ParseFile(Fixture("tiny_battery.json"));
        Assert.Equal("B0005", record.BatteryId);
        Assert.Equal(3, record.DischargeCycles.Count());
        Assert.True(record.DischargeCycles.First().HasTrace);
        Assert.True(record.DischargeCycles.First().CapacityAh > 1.5);
        Assert.False(record.RatedCapacityAssumed);
    }

    [Fact]
    public void CalceCsv_ReadsTwoDischargeCycles()
    {
        var record = CalceTableParser.ParseFile(Fixture("calce_sample.csv"), "CS2_TEST", ratedCapacityAh: 1.1);
        Assert.Equal("calce", record.Source);
        Assert.Equal(2, record.DischargeCycles.Count());
        Assert.True(record.DischargeCycles.First().CapacityAh > 0);
        Assert.True(record.RatedCapacityAssumed);
        Assert.NotNull(record.DischargeCycles.First().Features);
    }

    [Fact]
    public void Loader_RejectsMatWithHelpfulMessage()
    {
        var ex = Assert.Throws<NotSupportedException>(() => BatteryFileLoader.Load("B0005.mat"));
        Assert.Contains("Python", ex.Message);
    }
}
