using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.UI.Dispatching;

namespace BatteryHealth.App.ViewModels;

public sealed class TrajectorySnapshot
{
    public required BatteryRecord Battery { get; init; }
    public IReadOnlyList<ForecastResult> Points { get; init; } = [];
    public string? Error { get; init; }
}

/// <summary>Shared session for the three Fluent pages.</summary>
public partial class WorkspaceViewModel : ObservableObject
{
    private readonly object _gate = new();
    private BatteryAnalyticsService? _service;

    [ObservableProperty] private BatteryRecord? battery;
    [ObservableProperty] private BatteryCycle? selectedCycle;
    [ObservableProperty] private ForecastResult? forecast;
    [ObservableProperty] private string status = "Load a NASA processed JSON or a CALCE CSV/Excel log.";
    [ObservableProperty] private string? errorMessage;
    [ObservableProperty] private bool isBusy;
    [ObservableProperty] private string batteryTitle = "No battery loaded";
    [ObservableProperty] private string summaryLine = "Fleet diagnostic — local ONNX, no cloud.";
    [ObservableProperty] private TrajectorySnapshot? trajectory;
    [ObservableProperty] private double scenarioAmbientC = 24;
    [ObservableProperty] private double scenarioCRate = 1;

    public static string DemoPath => Path.Combine(AppContext.BaseDirectory, "Assets", "B0005.sample.json");

    public IReadOnlyList<BatteryCycle> DischargeCycles =>
        Battery?.DischargeCycles.ToList() ?? [];

    private int _ratedGeneration;

    public BatteryAnalyticsService Service => _service ??= new BatteryAnalyticsService();

    public event EventHandler? BatteryChanged;
    public event EventHandler? CycleChanged;

    [RelayCommand]
    public async Task LoadFromPath(string path)
    {
        var ui = DispatcherQueue.GetForCurrentThread();
        Post(ui, () =>
        {
            IsBusy = true;
            ErrorMessage = null;
            Status = "Loading…";
        });

        try
        {
            var loaded = await Task.Run(() =>
            {
                lock (_gate)
                {
                    var record = Service.Load(path);
                    IReadOnlyList<ForecastResult> points = [];
                    string? trajectoryError = null;
                    try
                    {
                        points = Service.ForecastTrajectory(record);
                    }
                    catch (Exception ex)
                    {
                        trajectoryError = ex.Message;
                    }

                    return (record, points, trajectoryError);
                }
            });

            Post(ui, () => ApplyLoaded(path, loaded.record, loaded.points, loaded.trajectoryError));
        }
        catch (Exception ex)
        {
            Post(ui, () =>
            {
                ErrorMessage = ex.Message;
                Status = "Could not load file.";
                IsBusy = false;
            });
        }
    }

    public void SelectCycle(int cycleIndex)
    {
        if (Battery is null)
        {
            return;
        }

        var next = Battery.DischargeAt(cycleIndex);
        if (next is null)
        {
            ErrorMessage = $"Cycle {cycleIndex} is not a discharge in this log.";
            return;
        }

        if (ReferenceEquals(next, SelectedCycle))
        {
            return;
        }

        SelectedCycle = next;
        RefreshForecast();
        CycleChanged?.Invoke(this, EventArgs.Empty);
    }

    public void RefreshForecast()
    {
        if (Battery is null || SelectedCycle is null)
        {
            Forecast = null;
            return;
        }

        try
        {
            lock (_gate)
            {
                Forecast = Service.Forecast(Battery, SelectedCycle.CycleIndex);
            }

            if (Trajectory?.Error is null)
            {
                ErrorMessage = null;
            }
        }
        catch (Exception ex)
        {
            Forecast = null;
            ErrorMessage = ex.Message;
        }
    }

    private void ApplyLoaded(
        string path,
        BatteryRecord record,
        IReadOnlyList<ForecastResult> points,
        string? trajectoryError)
    {
        var discharges = record.DischargeCycles.ToList();
        var first = discharges.FirstOrDefault()?.CapacityAh;
        var last = discharges.LastOrDefault()?.CapacityAh;
        Battery = record;
        Trajectory = new TrajectorySnapshot
        {
            Battery = record,
            Points = points,
            Error = trajectoryError,
        };
        BatteryTitle = $"{record.BatteryId} · {record.Source.ToUpperInvariant()}";
        WriteSummary(discharges, first, last);
        Status = $"Loaded {path}";
        ErrorMessage = trajectoryError;
        SelectedCycle = discharges.LastOrDefault(c => c.HasTrace) ?? discharges.LastOrDefault();
        try
        {
            RefreshForecast();
            OnPropertyChanged(nameof(DischargeCycles));
            BatteryChanged?.Invoke(this, EventArgs.Empty);
            CycleChanged?.Invoke(this, EventArgs.Empty);
        }
        finally
        {
            IsBusy = false;
        }
    }

    public async Task SetRatedCapacityAsync(double ampHours)
    {
        if (Battery is null || ampHours <= 0 || double.IsNaN(ampHours))
        {
            return;
        }

        var ratedChanged = Math.Abs(Battery.RatedCapacityAh - ampHours) > 1e-9;
        Battery.RatedCapacityAh = ampHours;
        Battery.RatedCapacityAssumed = false;
        var discharges = Battery.DischargeCycles.ToList();
        WriteSummary(discharges, discharges.FirstOrDefault()?.CapacityAh, discharges.LastOrDefault()?.CapacityAh);
        BatteryChanged?.Invoke(this, EventArgs.Empty);
        if (!ratedChanged)
        {
            return;
        }

        var generation = ++_ratedGeneration;
        var ui = DispatcherQueue.GetForCurrentThread();
        var battery = Battery;
        Post(ui, () =>
        {
            IsBusy = true;
            ErrorMessage = null;
            Status = "Updating nameplate…";
        });

        try
        {
            var points = await Task.Run(() =>
            {
                lock (_gate)
                {
                    return Service.ForecastTrajectory(battery);
                }
            });
            if (generation != _ratedGeneration)
            {
                return;
            }

            Post(ui, () =>
            {
                if (!ReferenceEquals(Battery, battery))
                {
                    return;
                }

                Trajectory = new TrajectorySnapshot { Battery = battery, Points = points };
                RefreshForecast();
                BatteryChanged?.Invoke(this, EventArgs.Empty);
                CycleChanged?.Invoke(this, EventArgs.Empty);
                Status = $"Nameplate set to {ampHours:0.00} Ah.";
                IsBusy = false;
            });
        }
        catch (Exception ex)
        {
            if (generation != _ratedGeneration)
            {
                return;
            }

            Post(ui, () =>
            {
                ErrorMessage = ex.Message;
                Status = "Could not refresh the forecast for the new nameplate.";
                IsBusy = false;
            });
        }
    }

    private void WriteSummary(IReadOnlyList<BatteryCycle> discharges, double? first, double? last)
    {
        if (Battery is null)
        {
            return;
        }

        var assumed = Battery.RatedCapacityAssumed ? " (assumed)" : "";
        SummaryLine =
            $"{discharges.Count} discharge cycles · rated {Battery.RatedCapacityAh:0.00} Ah{assumed} · " +
            $"EOL {Battery.EolCapacityFraction:P0} ({Battery.EolCapacityAh:0.00} Ah) · " +
            $"capacity {first:0.000} → {last:0.000} Ah";
    }

    private static void Post(DispatcherQueue? queue, Action action)
    {
        if (queue is null || queue.HasThreadAccess)
        {
            action();
            return;
        }

        queue.TryEnqueue(() => action());
    }
}
