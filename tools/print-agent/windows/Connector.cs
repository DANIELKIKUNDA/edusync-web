using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Printing;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using Timer = System.Windows.Forms.Timer;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Connector
{
    private const string Origin = "https://staging.myeducsync.com";
    private static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        if (args.Length == 2 && args[0] == "--approve" && args[1] == Origin)
        {
            using (var owner = new Form { TopMost = true, Opacity = 0, ShowInTaskbar = false })
            {
                owner.Show();
                var answer = MessageBox.Show(owner,
                    "Autoriser EduSync staging à imprimer les reçus sur ce poste ?",
                    "EduSync Print Connector", MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
                return answer == DialogResult.Yes ? 0 : 2;
            }
        }

        bool firstInstance;
        using (var mutex = new Mutex(true, @"Local\EduSyncPrintConnectorStaging", out firstInstance))
        {
            if (!firstInstance) return 0;
            try { return StartAgent(); }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "EduSync Print Connector", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }

    private static int StartAgent()
    {
        string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "EduSyncPrintConnectorStaging");
        Directory.CreateDirectory(data);
        string config = Path.Combine(data, "config.json");
        if (!File.Exists(config))
        {
            var printer = SelectPrinter();
            if (printer == null) return 0;
            byte[] bytes = new byte[32];
            using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
            string json = new JavaScriptSerializer().Serialize(new {
                origin = Origin,
                key = BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant(),
                printer = printer,
                renderer = Path.Combine(Root, "SumatraPDF.exe"),
                interactivePairing = true
            });
            string pending = config + ".tmp";
            File.WriteAllText(pending, json);
            File.Move(pending, config);
        }
        var options = new ProcessStartInfo {
            FileName = Path.Combine(Root, "node.exe"),
            Arguments = Quote(Path.Combine(Root, "server.mjs")) + " " + Quote(config),
            UseShellExecute = false,
            CreateNoWindow = true
        };
        using (var agent = Process.Start(options))
        {
            bool stopped = false;
            using (var menu = new ContextMenuStrip())
            using (var tray = new NotifyIcon { Icon = SystemIcons.Application,
                Text = "EduSync Print Connector (staging)", ContextMenuStrip = menu, Visible = true })
            using (var timer = new Timer { Interval = 1000 })
            {
                menu.Items.Add("Quitter le connecteur", null, delegate {
                    stopped = true;
                    Application.ExitThread();
                });
                timer.Tick += delegate { if (agent.HasExited) Application.ExitThread(); };
                timer.Start();
                try { Application.Run(); }
                finally
                {
                    if (!agent.HasExited)
                    {
                        try { agent.Kill(); }
                        catch (InvalidOperationException) { if (!agent.HasExited) throw; }
                        agent.WaitForExit();
                    }
                    tray.Visible = false;
                }
            }
            if (stopped) return 0;
            if (agent.ExitCode != 0)
                throw new InvalidOperationException("Le connecteur n’a pas démarré. Fermez l’ancien agent d’impression EduSync s’il est ouvert, puis relancez le connecteur.");
            return agent.ExitCode;
        }
    }

    private static string Quote(string value) { return "\"" + value + "\""; }

    private static string SelectPrinter()
    {
        using (var dialog = new Form { Text = "EduSync Print Connector", Width = 420, Height = 150,
            StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false, MinimizeBox = false })
        {
            var label = new Label { Text = "Sélectionnez l’imprimante des reçus", Left = 12, Top = 12, AutoSize = true };
            var printers = new ComboBox { Left = 12, Top = 36, Width = 380, DropDownStyle = ComboBoxStyle.DropDownList };
            foreach (string printer in PrinterSettings.InstalledPrinters) printers.Items.Add(printer);
            if (printers.Items.Count == 0)
                throw new InvalidOperationException("Installez d’abord le pilote de l’imprimante dans Windows.");
            printers.SelectedIndex = 0;
            var confirm = new Button { Text = "Continuer", Left = 287, Top = 68, Width = 105, DialogResult = DialogResult.OK };
            dialog.Controls.AddRange(new Control[] { label, printers, confirm });
            dialog.AcceptButton = confirm;
            return dialog.ShowDialog() == DialogResult.OK ? (string)printers.SelectedItem : null;
        }
    }
}
