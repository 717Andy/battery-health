using BatteryHealth.Core.Features;

namespace BatteryHealth.Core.Inference;

public static class ModelLocator
{
    public static string? FindDirectory(string? overridePath = null)
    {
        if (!string.IsNullOrWhiteSpace(overridePath) && Directory.Exists(overridePath))
        {
            return overridePath;
        }

        var env = Environment.GetEnvironmentVariable("BATTERYHEALTH_MODELS");
        if (!string.IsNullOrWhiteSpace(env) && Directory.Exists(env))
        {
            return env;
        }

        foreach (var candidate in Candidates())
        {
            if (File.Exists(Path.Combine(candidate, "soh.onnx")) && File.Exists(Path.Combine(candidate, "rul.onnx")))
            {
                return candidate;
            }
        }

        return null;
    }

    public static (string Soh, string Rul, FeatureSpec Spec) Resolve(string? overridePath = null)
    {
        var dir = FindDirectory(overridePath)
                  ?? throw new FileNotFoundException(
                      "Could not find soh.onnx / rul.onnx. Train models or set BATTERYHEALTH_MODELS.");
        var specPath = Path.Combine(dir, "feature_spec.json");
        var spec = File.Exists(specPath) ? FeatureSpec.Load(specPath) : FeatureSpec.Default;
        return (Path.Combine(dir, spec.Soh.Model), Path.Combine(dir, spec.Rul.Model), spec);
    }

    private static IEnumerable<string> Candidates()
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var list = new List<string>();

        void Push(string? path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            var full = Path.GetFullPath(path);
            if (seen.Add(full))
            {
                list.Add(full);
            }
        }

        Push(Path.Combine(AppContext.BaseDirectory, "Models"));
        Push(Path.Combine(AppContext.BaseDirectory, "artifacts", "models"));
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && dir is not null; i++, dir = dir.Parent)
        {
            Push(Path.Combine(dir.FullName, "artifacts", "models"));
            Push(Path.Combine(dir.FullName, "Models"));
        }

        return list;
    }
}
