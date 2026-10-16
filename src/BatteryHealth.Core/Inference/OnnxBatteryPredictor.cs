using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Features;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;

namespace BatteryHealth.Core.Inference;

public sealed class OnnxBatteryPredictor : IDisposable
{
    private readonly InferenceSession _soh;
    private readonly InferenceSession _rul;
    private readonly FeatureSpec _spec;

    public FeatureSpec Spec => _spec;

    public OnnxBatteryPredictor(string? modelDirectory = null)
    {
        var (sohPath, rulPath, spec) = ModelLocator.Resolve(modelDirectory);
        _spec = spec;
        var options = new SessionOptions();
        _soh = new InferenceSession(sohPath, options);
        _rul = new InferenceSession(rulPath, options);
    }

    public ForecastResult Predict(BatteryRecord battery, BatteryCycle cycle, double? sohOverride = null)
    {
        var labelSoh = cycle.ObservedSoh(battery.RatedCapacityAh);
        // The RUL head was trained on SoH = capacity / 2.0 Ah. A corrected nameplate
        // changes the label and the fade thresholds, not that model input.
        var modelSoh = cycle.ObservedSoh(BatteryRecord.TrainingRatedCapacityAh);
        Dictionary<string, double> features;
        if (cycle.HasTrace)
        {
            features = CycleFeatureExtractor.Extract(cycle, modelSoh ?? sohOverride);
        }
        else if (cycle.Features is { Count: > 0 })
        {
            features = new Dictionary<string, double>(cycle.Features, StringComparer.Ordinal);
        }
        else
        {
            throw new InvalidOperationException($"Cycle {cycle.CycleIndex} has neither a sensor trace nor precomputed features.");
        }

        var sohVec = CycleFeatureExtractor.Vector(features, _spec.Soh.Columns.Count > 0 ? _spec.Soh.Columns : CycleFeatureExtractor.SohColumns);
        var predictedSoh = sohOverride ?? Run(_soh, _spec.Soh.InputName, sohVec);
        predictedSoh = Math.Clamp(predictedSoh, 0, 1.5);
        features["soh"] = modelSoh ?? predictedSoh;

        var rulVec = CycleFeatureExtractor.Vector(features, _spec.Rul.Columns.Count > 0 ? _spec.Rul.Columns : CycleFeatureExtractor.RulColumns);
        var rul = Math.Max(0, Run(_rul, _spec.Rul.InputName, rulVec));

        return new ForecastResult
        {
            BatteryId = battery.BatteryId,
            CycleIndex = cycle.CycleIndex,
            PredictedSoh = predictedSoh,
            ObservedSoh = labelSoh,
            PredictedRulCycles = rul,
            EolCapacityFraction = battery.EolCapacityFraction,
            EolCapacityAh = battery.EolCapacityAh,
            Features = features,
        };
    }

    public IReadOnlyList<ForecastResult> PredictAll(BatteryRecord battery) =>
        battery.DischargeCycles.Select(c => Predict(battery, c)).ToList();

    private static double Run(InferenceSession session, string inputName, float[] values)
    {
        var name = string.IsNullOrWhiteSpace(inputName) ? session.InputMetadata.Keys.First() : inputName;
        var tensor = new DenseTensor<float>(values, [1, values.Length]);
        using var results = session.Run([NamedOnnxValue.CreateFromTensor(name, tensor)]);
        var raw = results[0].Value;
        return raw switch
        {
            DenseTensor<float> ft => ft.Length > 0 ? ft.ToArray()[0] : 0,
            Tensor<float> t => t[0],
            IEnumerable<float> en => en.First(),
            DenseTensor<double> dt => dt.Length > 0 ? (float)dt.ToArray()[0] : 0,
            _ => Convert.ToDouble(results[0].AsEnumerable<float>().First()),
        };
    }

    public void Dispose()
    {
        _soh.Dispose();
        _rul.Dispose();
    }
}
