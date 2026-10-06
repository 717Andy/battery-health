using BatteryHealth.Core.Inference;
using BatteryHealth.Core.Parsing;

namespace BatteryHealth.Core.Tests;

public class OnnxInferenceTests
{
    [Fact]
    public void PredictsSohAndRul_OnNasaSample()
    {
        var dir = ModelLocator.FindDirectory();
        Assert.NotNull(dir);
        using var predictor = new OnnxBatteryPredictor(dir);
        var battery = CanonicalJsonParser.ParseFile(Path.Combine(AppContext.BaseDirectory, "fixtures", "tiny_battery.json"));
        var cycle = battery.DischargeCycles.First();
        var result = predictor.Predict(battery, cycle);
        Assert.InRange(result.PredictedSoh, 0.6, 1.2);
        Assert.True(result.PredictedRulCycles > 0);
        Assert.Equal(0.70, result.EolCapacityFraction);
        if (result.ObservedSoh is { } observed)
        {
            Assert.InRange(Math.Abs(result.PredictedSoh - observed), 0, 0.08);
        }
    }
}
