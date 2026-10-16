using System.Text.Json;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Features;
using BatteryHealth.Core.Inference;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;

namespace BatteryHealth.Core.Tests;

public class GoldenParityTests
{
    [Fact]
    public void Features_And_Onnx_MatchPythonGolden()
    {
        using var cycleDoc = JsonDocument.Parse(File.ReadAllText(Fixture("golden_cycle.json")));
        using var expectedDoc = JsonDocument.Parse(File.ReadAllText(Fixture("golden_expected.json")));
        var cycle = cycleDoc.RootElement;
        var expected = expectedDoc.RootElement;
        var atolFeatures = expected.GetProperty("atolFeatures").GetDouble();
        var atolOnnx = expected.GetProperty("atolOnnx").GetDouble();

        var feats = CycleFeatureExtractor.Extract(
            cycle.GetProperty("cycleIndex").GetInt32(),
            Doubles(cycle, "timeS"),
            Doubles(cycle, "voltageV"),
            Doubles(cycle, "currentA"),
            Doubles(cycle, "temperatureC"),
            cycle.GetProperty("ambientTemperatureC").GetDouble(),
            cycle.GetProperty("soh").GetDouble());

        foreach (var column in expected.GetProperty("features").EnumerateObject())
        {
            Assert.True(feats.ContainsKey(column.Name), column.Name);
            Assert.InRange(Math.Abs(feats[column.Name] - column.Value.GetDouble()), 0, atolFeatures);
        }

        var dir = ModelLocator.FindDirectory();
        Assert.NotNull(dir);
        var soh = RunOnnx(Path.Combine(dir!, "soh.onnx"), CycleFeatureExtractor.Vector(feats, CycleFeatureExtractor.SohColumns));
        var rul = RunOnnx(Path.Combine(dir, "rul.onnx"), CycleFeatureExtractor.Vector(feats, CycleFeatureExtractor.RulColumns));
        Assert.InRange(Math.Abs(soh - expected.GetProperty("sohOnnx").GetDouble()), 0, atolOnnx);
        Assert.InRange(Math.Abs(rul - expected.GetProperty("rulOnnx").GetDouble()), 0, atolOnnx);
    }

    [Fact]
    public void ModelCard_SeparatesShippedFitFromHoldoutFit()
    {
        var dir = ModelLocator.FindDirectory();
        Assert.NotNull(dir);
        var spec = FeatureSpec.Load(Path.Combine(dir!, "feature_spec.json"));
        Assert.Equal("all-rows", spec.Card.FitScope);
        Assert.Equal("holdout-excluded", spec.Card.HoldoutMetricsFitScope);
        Assert.Contains("GradientBoostingRegressor", spec.Card.Family);
        Assert.Equal(636, spec.Card.NRows);
        Assert.Contains("B0007", spec.Card.Batteries);

        var metricsPath = Path.GetFullPath(Path.Combine(dir, "..", "metrics.json"));
        using var metrics = JsonDocument.Parse(File.ReadAllText(metricsPath));
        var root = metrics.RootElement;
        Assert.Equal("all-rows", root.GetProperty("productionModel").GetProperty("fitScope").GetString());
        Assert.Equal("in-sample", root.GetProperty("noiseRobustness").GetProperty("0.0").GetProperty("scope").GetString());
        Assert.Contains(
            "B0007",
            root.GetProperty("eolCensoring").GetProperty("censoredBatteries").EnumerateArray().Select(x => x.GetString()));
        Assert.True(root.GetProperty("rulNestedSoh").TryGetProperty("pooledExcludingCensored", out _));
    }

    [Fact]
    public void Predictor_Soh_MatchesGoldenWhenCapacityIsAbsent()
    {
        using var cycleDoc = JsonDocument.Parse(File.ReadAllText(Fixture("golden_cycle.json")));
        using var expectedDoc = JsonDocument.Parse(File.ReadAllText(Fixture("golden_expected.json")));
        var cycleJson = cycleDoc.RootElement;
        var battery = new BatteryRecord
        {
            BatteryId = "GOLDEN",
            RatedCapacityAh = 2.0,
            Cycles =
            [
                new BatteryCycle
                {
                    CycleIndex = cycleJson.GetProperty("cycleIndex").GetInt32(),
                    Type = "discharge",
                    AmbientTemperatureC = cycleJson.GetProperty("ambientTemperatureC").GetDouble(),
                    TimeS = Doubles(cycleJson, "timeS"),
                    VoltageV = Doubles(cycleJson, "voltageV"),
                    CurrentA = Doubles(cycleJson, "currentA"),
                    TemperatureC = Doubles(cycleJson, "temperatureC"),
                },
            ],
        };
        using var predictor = new OnnxBatteryPredictor(ModelLocator.FindDirectory());
        var result = predictor.Predict(battery, battery.Cycles[0]);
        var atol = expectedDoc.RootElement.GetProperty("atolOnnx").GetDouble();
        Assert.InRange(Math.Abs(result.PredictedSoh - expectedDoc.RootElement.GetProperty("sohOnnx").GetDouble()), 0, atol);
    }

    private static string Fixture(string name) => Path.Combine(AppContext.BaseDirectory, "fixtures", name);

    private static List<double> Doubles(JsonElement parent, string name) =>
        parent.GetProperty(name).EnumerateArray().Select(x => x.GetDouble()).ToList();

    private static double RunOnnx(string modelPath, float[] values)
    {
        using var session = new InferenceSession(modelPath);
        var inputName = session.InputMetadata.Keys.First();
        var tensor = new DenseTensor<float>(values, [1, values.Length]);
        using var results = session.Run([NamedOnnxValue.CreateFromTensor(inputName, tensor)]);
        return results[0].AsEnumerable<float>().First();
    }
}
