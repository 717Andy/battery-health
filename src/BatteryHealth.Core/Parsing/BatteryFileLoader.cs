using BatteryHealth.Core.Domain;

namespace BatteryHealth.Core.Parsing;

public static class BatteryFileLoader
{
    public static BatteryRecord Load(string path)
    {
        var ext = Path.GetExtension(path).ToLowerInvariant();
        return ext switch
        {
            ".json" => CanonicalJsonParser.ParseFile(path),
            ".csv" or ".xlsx" or ".xls" => CalceTableParser.ParseFile(path),
            ".mat" => throw new NotSupportedException(
                "NASA .mat files are parsed by the Python pipeline (python -m batteryhealth.download). " +
                "Load the resulting data/processed/*.json here, or POST the .mat to the FastAPI /parse/nasa endpoint."),
            _ => throw new NotSupportedException($"Unsupported battery file type: {ext}"),
        };
    }
}
