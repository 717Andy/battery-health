using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;

namespace BatteryHealth.App;

public partial class App : Application
{
    public static MainWindow? MainWindow { get; private set; }
    public static WorkspaceViewModel Workspace { get; } = new();

    public App()
    {
        InitializeComponent();
        UnhandledException += (_, e) =>
        {
            Workspace.ErrorMessage = e.Exception.Message;
            e.Handled = true;
        };
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        MainWindow = new MainWindow();
        MainWindow.Activate();
    }
}
