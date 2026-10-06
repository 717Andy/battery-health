using System.Text.Json;
using System.Text.Json.Serialization;

namespace BatteryHealth.Core.Features;

public sealed class FeatureSpec
{
    [JsonPropertyName("soh")]
    public ModelIo Soh { get; set; } = new();

    [JsonPropertyName("rul")]
    public ModelIo Rul { get; set; } = new();

    [JsonPropertyName("eolCapacityFraction")]
    public double EolCapacityFraction { get; set; } = 0.70;

    [JsonPropertyName("eolCapacityFractionOem")]
    public double EolCapacityFractionOem { get; set; } = 0.80;

    [JsonPropertyName("ratedCapacityAh")]
    public double RatedCapacityAh { get; set; } = 2.0;

    [JsonPropertyName("notes")]
    public string? Notes { get; set; }

    public static FeatureSpec Load(string path) =>
        JsonSerializer.Deserialize<FeatureSpec>(File.ReadAllText(path), JsonOptions)
        ?? throw new InvalidOperationException($"Could not read feature spec from {path}");

    public static FeatureSpec Default { get; } = new()
    {
        Soh = new ModelIo { Model = "soh.onnx", InputName = "features", OutputName = "variable", Columns = CycleFeatureExtractor.SohColumns.ToList() },
        Rul = new ModelIo { Model = "rul.onnx", InputName = "features", OutputName = "variable", Columns = CycleFeatureExtractor.RulColumns.ToList() },
    };

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };
}

public sealed class ModelIo
{
    [JsonPropertyName("model")]
    public string Model { get; set; } = "";

    [JsonPropertyName("inputName")]
    public string InputName { get; set; } = "features";

    [JsonPropertyName("outputName")]
    public string OutputName { get; set; } = "variable";

    [JsonPropertyName("columns")]
    public List<string> Columns { get; set; } = [];
}
