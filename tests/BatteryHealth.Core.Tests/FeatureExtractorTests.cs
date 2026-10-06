using BatteryHealth.Core.Features;

namespace BatteryHealth.Core.Tests;

public class FeatureExtractorTests
{
    [Fact]
    public void TimeToVoltage_InterpolatesCrossing()
    {
        var t = new[] { 0.0, 10.0, 20.0 };
        var v = new[] { 4.0, 3.5, 3.0 };
        Assert.Equal(10.0, CycleFeatureExtractor.TimeToVoltage(t, v, 3.5), 6);
        Assert.Equal(20.0, CycleFeatureExtractor.TimeToVoltage(t, v, 3.0), 6);
    }

    [Fact]
    public void Extract_MatchesExpectedShapeAndNoCapacityLeak()
    {
        var feats = CycleFeatureExtractor.Extract(
            3,
            [0, 60, 120, 180, 240],
            [4.1, 3.9, 3.6, 3.3, 2.9],
            [-2, -2, -2, -2, -2],
            [24, 25, 26, 27, 28],
            24,
            0.92);
        Assert.Equal(3, feats["cycle_index"]);
        Assert.True(feats["voltage_max"] > feats["voltage_min"]);
        Assert.Equal(240, feats["duration_s"]);
        Assert.Equal(4.0, feats["temp_rise"]);
        Assert.Equal(0.92, feats["soh"]);
        Assert.False(feats.ContainsKey("capacity"));
        var vec = CycleFeatureExtractor.Vector(feats, CycleFeatureExtractor.SohColumns);
        Assert.Equal(CycleFeatureExtractor.SohColumns.Length, vec.Length);
    }
}
