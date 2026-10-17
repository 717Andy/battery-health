using BatteryHealth.Core.Domain;
using LiveChartsCore;
using LiveChartsCore.Defaults;
using LiveChartsCore.Measure;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Painting;
using SkiaSharp;

namespace BatteryHealth.App.Charts;

/// <summary>
/// LiveCharts2 helpers. OxyPlot.Windows targets UWP / WinUI 2 and does not
/// officially support WinUI 3, so the desktop app uses LiveChartsCore.
/// </summary>
public static class ChartFactory
{
    private static readonly SolidColorPaint Teal = new(SKColor.Parse("#0F766E"));
    private static readonly SolidColorPaint Amber = new(SKColor.Parse("#D97706"));
    private static readonly SolidColorPaint Rose = new(SKColor.Parse("#BE123C"));
    private static readonly SolidColorPaint Slate = new(SKColor.Parse("#64748B"));
    private static readonly SolidColorPaint TealBand = new(new SKColor(15, 118, 110, 48));

    public static ISeries[] SensorSeries(BatteryCycle? cycle)
    {
        if (cycle is null || !cycle.HasTrace)
        {
            return [];
        }

        return
        [
            Line("Voltage (V)", cycle.TimeS, cycle.VoltageV, Teal, scalesYAt: 0),
            Line("Current (A)", cycle.TimeS, cycle.CurrentA, Amber, scalesYAt: 1),
            Line("Temperature (°C)", cycle.TimeS, cycle.TemperatureC, Rose, scalesYAt: 1),
        ];
    }

    public static ISeries[] FadeSeries(BatteryRecord? battery, IReadOnlyList<FadePoint>? stressed = null, int? selectedCycle = null)
    {
        if (battery is null)
        {
            return [];
        }

        var baseline = battery.DischargeCycles
            .Where(c => c.CapacityAh.HasValue)
            .Select(c => new ObservablePoint(c.CycleIndex, c.CapacityAh))
            .ToArray();

        var series = new List<ISeries>
        {
            new LineSeries<ObservablePoint>
            {
                Name = "Measured capacity",
                Values = baseline,
                Fill = null,
                Stroke = Teal,
                GeometrySize = 0,
                LineSmoothness = 0.15,
            },
        };

        if (stressed is { Count: > 0 })
        {
            series.Add(new LineSeries<ObservablePoint>
            {
                Name = "Stressed capacity",
                Values = stressed.Select(p => new ObservablePoint(p.CycleIndex, p.CapacityAh)).ToArray(),
                Fill = null,
                Stroke = Rose,
                GeometrySize = 0,
                LineSmoothness = 0.15,
            });
        }

        if (baseline.Length > 0)
        {
            var first = baseline[0].X ?? 0;
            var last = baseline[^1].X ?? first;
            series.Add(Threshold("70% of nameplate", first, last, battery.RatedCapacityAh * 0.70, Amber));
            series.Add(Threshold("80% of nameplate", first, last, battery.RatedCapacityAh * 0.80, Slate));
        }

        if (selectedCycle is { } chosen)
        {
            var mark = baseline.FirstOrDefault(point => point.X is { } x && Math.Abs(x - chosen) < 0.5);
            if (mark is not null)
            {
                series.Add(new ScatterSeries<ObservablePoint>
                {
                    Name = "Selected cycle",
                    Values = [new ObservablePoint(mark.X, mark.Y)],
                    GeometrySize = 14,
                    Fill = Rose,
                    Stroke = Rose,
                });
            }
        }

        return series.ToArray();
    }

    private static LineSeries<ObservablePoint> Threshold(string name, double first, double last, double capacityAh, SolidColorPaint paint) =>
        new()
        {
            Name = name,
            Values = [new ObservablePoint(first, capacityAh), new ObservablePoint(last, capacityAh)],
            Fill = null,
            Stroke = paint,
            GeometrySize = 0,
            LineSmoothness = 0,
            StrokeDashArray = [6, 4],
        };

    public static ISeries[] SohSeries(
        IReadOnlyList<ForecastResult> forecasts,
        BatteryRecord battery,
        int? selectedCycle = null,
        double? sohHoldoutRmse = null)
    {
        _ = battery;
        var ordered = forecasts.OrderBy(point => point.CycleIndex).ToList();
        var predicted = ordered.Select(f => new ObservablePoint(f.CycleIndex, f.PredictedSoh * 100)).ToArray();
        var observed = ordered
            .Where(f => f.ObservedSoh.HasValue)
            .Select(f => new ObservablePoint(f.CycleIndex, f.ObservedSoh!.Value * 100))
            .ToArray();
        var series = new List<ISeries>();
        if (sohHoldoutRmse is { } rmse && ordered.Count > 0)
        {
            var band = new List<ObservablePoint>(ordered.Count * 2);
            foreach (var point in ordered)
            {
                band.Add(new ObservablePoint(point.CycleIndex, (point.PredictedSoh + rmse) * 100));
            }

            for (var i = ordered.Count - 1; i >= 0; i--)
            {
                band.Add(new ObservablePoint(ordered[i].CycleIndex, (ordered[i].PredictedSoh - rmse) * 100));
            }

            series.Add(new LineSeries<ObservablePoint>
            {
                Name = "Typical protocol miss",
                Values = band.ToArray(),
                Stroke = null,
                Fill = TealBand,
                GeometrySize = 0,
                LineSmoothness = 0,
            });
        }

        series.Add(new LineSeries<ObservablePoint>
        {
            Name = "Predicted SoH %",
            Values = predicted,
            Fill = null,
            Stroke = Teal,
            GeometrySize = 0,
        });
        series.Add(new LineSeries<ObservablePoint>
        {
            Name = "Measured SoH %",
            Values = observed,
            Fill = null,
            Stroke = Slate,
            GeometrySize = 0,
            StrokeDashArray = [4, 3],
        });

        if (selectedCycle is { } chosen)
        {
            var mark = ordered.FirstOrDefault(point => point.CycleIndex == chosen);
            if (mark is not null)
            {
                series.Add(new ScatterSeries<ObservablePoint>
                {
                    Name = "Selected cycle",
                    Values = [new ObservablePoint(mark.CycleIndex, mark.PredictedSoh * 100)],
                    GeometrySize = 14,
                    Fill = Rose,
                    Stroke = Rose,
                });
            }
        }

        return series.ToArray();
    }

    public static Axis[] TimeAxis() => [new Axis { Name = "Time (s)" }];
    public static Axis[] CycleAxis() => [new Axis { Name = "Cycle" }];
    public static Axis[] SensorYAxis() =>
    [
        new Axis { Name = "Voltage (V)", Position = AxisPosition.Start },
        new Axis { Name = "Current (A) and temperature (°C)", Position = AxisPosition.End },
    ];
    public static Axis[] CapacityAxis() => [new Axis { Name = "Capacity (Ah)" }];
    public static Axis[] SohAxis() => [new Axis { Name = "SoH (%)" }];

    private static LineSeries<ObservablePoint> Line(string name, IReadOnlyList<double> x, IReadOnlyList<double> y, SolidColorPaint paint, int scalesYAt = 0)
    {
        var n = Math.Min(x.Count, y.Count);
        var points = new ObservablePoint[n];
        for (var i = 0; i < n; i++)
        {
            points[i] = new ObservablePoint(x[i], y[i]);
        }

        return new LineSeries<ObservablePoint>
        {
            Name = name,
            Values = points,
            Fill = null,
            Stroke = paint,
            GeometrySize = 0,
            LineSmoothness = 0.2,
            ScalesYAt = scalesYAt,
        };
    }
}
