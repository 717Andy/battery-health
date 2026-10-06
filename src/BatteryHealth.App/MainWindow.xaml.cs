using BatteryHealth.App.ViewModels;
using BatteryHealth.App.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace BatteryHealth.App;

public sealed partial class MainWindow : Window
{
    public WorkspaceViewModel Workspace => App.Workspace;

    public MainWindow()
    {
        InitializeComponent();
        Title = "BatteryHealth";
        SystemBackdrop = new MicaBackdrop();
        Nav.SelectedItem = Nav.MenuItems[0];
        ContentFrame.Navigate(typeof(DashboardPage));
        ExtendsContentIntoTitleBar = true;
    }

    private void OnItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
    {
        var tag = (args.InvokedItemContainer as NavigationViewItem)?.Tag as string;
        switch (tag)
        {
            case "forecast":
                ContentFrame.Navigate(typeof(ForecastPage));
                break;
            case "simulator":
                ContentFrame.Navigate(typeof(SimulatorPage));
                break;
            default:
                ContentFrame.Navigate(typeof(DashboardPage));
                break;
        }
    }
}
