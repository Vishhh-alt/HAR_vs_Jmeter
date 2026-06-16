package com.visvashwarr.jmeter.listener;

import org.apache.jmeter.samplers.SampleResult;
import org.apache.jmeter.testelement.AbstractTestElement;
import org.apache.jmeter.testelement.TestStateListener;
import org.apache.jmeter.visualizers.gui.AbstractListenerGui;
import org.apache.jmeter.samplers.Clearable;
import org.apache.jmeter.samplers.Remoteable;
import org.apache.jmeter.visualizers.Visualizer;

import javax.swing.*;
import javax.swing.border.EmptyBorder;
import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * HAR vs JMeter Listener
 *
 * A JMeter Listener that:
 * 1. Collects all sampler results during the test run
 * 2. At test end, reads a HAR file you specify
 * 3. Matches HAR requests to JMeter samplers by URL path
 * 4. Generates a rich HTML comparison report
 *
 * Author: Visvashwarr Venugopal · Performance Engineer
 */
public class HarVsJmeterListener extends AbstractListenerGui
        implements Visualizer, Clearable, Remoteable, TestStateListener {

    private static final long serialVersionUID = 1L;

    // ── Config keys ──────────────────────────────────────────
    static final String HAR_FILE_PATH   = "HarVsJmeter.harFilePath";
    static final String OUTPUT_DIR      = "HarVsJmeter.outputDir";
    static final String AUTO_OPEN       = "HarVsJmeter.autoOpen";
    static final String PYTHON_PATH     = "HarVsJmeter.pythonPath";
    static final String MODE            = "HarVsJmeter.mode";          // "live" or "offline"
    static final String CSV_FILE_PATH   = "HarVsJmeter.csvFilePath";    // used in offline mode

    static final String MODE_LIVE    = "live";
    static final String MODE_OFFLINE = "offline";

    /**
     * Property key used to link a running TestElement clone back to the
     * GUI instance that configured it. AbstractTestElement.clone() only
     * copies JMeter properties (not plain Java fields), so a direct object
     * reference would be lost on the clone JMeter uses for execution.
     * Storing a UUID as a property survives clone(); the element looks up
     * the GUI instance from REGISTRY using this ID.
     */
    static final String INSTANCE_ID = "HarVsJmeter.instanceId";

    /** Registry of live GUI instances, keyed by their instanceId. */
    static final Map<String, HarVsJmeterListener> REGISTRY = new java.util.concurrent.ConcurrentHashMap<>();

    /** Unique ID for this GUI instance — written into the TestElement's properties. */
    private final String instanceId = java.util.UUID.randomUUID().toString();

    // ── UI components ─────────────────────────────────────────
    private JTextField harFileField;
    private JTextField outputDirField;
    private JTextField pythonField;
    private JTextField csvFileField;
    private JCheckBox autoOpenCheck;
    private JRadioButton liveModeRadio;
    private JRadioButton offlineModeRadio;
    private JLabel csvFileLabel;
    private JButton csvBrowseBtn;
    private JButton runOfflineBtn;
    private JTextArea logArea;
    private JLabel statusLabel;

    // ── Runtime state ─────────────────────────────────────────
    private final Queue<SampleResult> results = new ConcurrentLinkedQueue<>();
    private long testStartTime;

    // ─────────────────────────────────────────────────────────
    // CONSTRUCTOR
    // ─────────────────────────────────────────────────────────

    public HarVsJmeterListener() {
        super();
        REGISTRY.put(instanceId, this);
        init();
    }

    // ─────────────────────────────────────────────────────────
    // JMETER REQUIRED METHODS
    // ─────────────────────────────────────────────────────────

    @Override
    public String getStaticLabel() {
        return "HAR vs JMeter Listener";
    }

    @Override
    public String getLabelResource() {
        return "har_vs_jmeter_listener";
    }

    @Override
    public void add(SampleResult result) {
        results.add(result);
        SwingUtilities.invokeLater(() ->
            statusLabel.setText("Collected " + results.size() + " samples...")
        );
    }

    @Override
    public void clearData() {
        results.clear();
        logArea.setText("");
        statusLabel.setText("Ready.");
    }

    @Override
    public boolean isStats() {
        return false;
    }

    // ─────────────────────────────────────────────────────────
    // TEST LIFECYCLE
    // ─────────────────────────────────────────────────────────

    @Override
    public void testStarted() {
        testStartTime = System.currentTimeMillis();
        int previousCount = results.size();
        results.clear();
        if (previousCount > 0) {
            log("Test started. Cleared " + previousCount + " sample(s) from previous run.");
        } else {
            log("Test started.");
        }
    }

    @Override
    public void testStarted(String host) {
        testStarted();
    }

    @Override
    public void testEnded() {
        log("Test ended. Collected " + results.size() + " samples.");
        if (offlineModeRadio != null && offlineModeRadio.isSelected()) {
            log("Offline mode selected — skipping auto report. Use 'Run Comparison' button to compare HAR with a saved CSV anytime.");
            return;
        }
        generateReport();
    }

    @Override
    public void testEnded(String host) {
        testEnded();
    }

    // ─────────────────────────────────────────────────────────
    // REPORT GENERATION
    // ─────────────────────────────────────────────────────────

    private void generateReport() {
        String harPath   = harFileField.getText().trim();
        String outputDir = outputDirField.getText().trim();
        String pythonExe = pythonField.getText().trim();
        boolean autoOpen = autoOpenCheck.isSelected();
        boolean offline  = offlineModeRadio != null && offlineModeRadio.isSelected();

        if (harPath.isEmpty()) {
            log("ERROR: No HAR file specified. Please set the HAR file path.");
            return;
        }
        if (!new File(harPath).exists()) {
            log("ERROR: HAR file not found: " + harPath);
            return;
        }

        String csvPath;

        if (offline) {
            // Offline mode — use the user-provided JMeter Summary Report CSV
            csvPath = csvFileField.getText().trim();
            if (csvPath.isEmpty()) {
                log("ERROR: No JMeter Summary Report CSV specified for offline mode.");
                return;
            }
            if (!new File(csvPath).exists()) {
                log("ERROR: CSV file not found: " + csvPath);
                return;
            }
            log("Offline mode — using existing summary report: " + csvPath);
        } else {
            // Live mode — auto-generate CSV from samples collected during the test run
            File tempCsv = writeTempCsv();
            if (tempCsv == null) return;
            csvPath = tempCsv.getAbsolutePath();
        }

        // Output report path
        String ts = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        String reportPath = (outputDir.isEmpty() ? System.getProperty("user.home") : outputDir)
                + File.separator + "har_vs_jmeter_" + ts + ".html";

        // Call Python script
        runPythonScript(pythonExe, harPath, csvPath, reportPath, autoOpen);
    }

    private File writeTempCsv() {
        try {
            File tmp = File.createTempFile("jmeter_summary_", ".csv");
            tmp.deleteOnExit();

            // Aggregate by label
            Map<String, long[]> agg = new LinkedHashMap<>();
            // long[]: 0=count, 1=totalTime, 2=min, 3=max, 4=errors, 5=totalBytes
            for (SampleResult r : results) {
                String label = r.getSampleLabel();
                agg.computeIfAbsent(label, k -> new long[]{0, 0, Long.MAX_VALUE, 0, 0, 0});
                long[] s = agg.get(label);
                s[0]++;
                s[1] += r.getTime();
                if (r.getTime() < s[2]) s[2] = r.getTime();
                if (r.getTime() > s[3]) s[3] = r.getTime();
                if (!r.isSuccessful()) s[4]++;
                s[5] += r.getBytesAsLong();
            }

            try (PrintWriter pw = new PrintWriter(new FileWriter(tmp))) {
                pw.println("Label,# Samples,Average,Min,Max,Std. Dev.,Error %,Throughput,Received KB/sec,Sent KB/sec,Avg. Bytes");
                for (Map.Entry<String, long[]> e : agg.entrySet()) {
                    long[] s = e.getValue();
                    long count = s[0];
                    double avg  = count > 0 ? (double) s[1] / count : 0;
                    double errP = count > 0 ? (double) s[4] / count * 100 : 0;
                    double avgB = count > 0 ? (double) s[5] / count : 0;
                    pw.printf("%s,%d,%.1f,%d,%d,0,%.2f%%,0,0,0,%.0f%n",
                            e.getKey(), count, avg, s[2], s[3], errP, avgB);
                }
            }
            log("Wrote temp CSV: " + tmp.getAbsolutePath());
            return tmp;
        } catch (Exception ex) {
            log("ERROR writing CSV: " + ex.getMessage());
            return null;
        }
    }

    private void runPythonScript(String pythonExe, String harPath,
                                  String csvPath, String reportPath, boolean autoOpen) {
        // Get path to bundled Python script
        String scriptPath = extractPythonScript();
        if (scriptPath == null) return;

        String python = pythonExe.isEmpty() ? "python" : pythonExe;

        List<String> cmd = Arrays.asList(python, scriptPath, harPath, csvPath, reportPath);
        log("Running: " + String.join(" ", cmd));

        new Thread(() -> {
            try {
                ProcessBuilder pb = new ProcessBuilder(cmd);
                pb.redirectErrorStream(true);
                Process proc = pb.start();

                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(proc.getInputStream()))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        final String l = line;
                        SwingUtilities.invokeLater(() -> log(l));
                    }
                }

                int exit = proc.waitFor();
                if (exit == 0) {
                    SwingUtilities.invokeLater(() -> {
                        log("✓ Report saved: " + reportPath);
                        statusLabel.setText("Report ready: " + reportPath);
                        if (autoOpen) openInBrowser(reportPath);
                    });
                } else {
                    SwingUtilities.invokeLater(() -> log("ERROR: Python script exited with code " + exit));
                }
            } catch (Exception ex) {
                SwingUtilities.invokeLater(() -> log("ERROR: " + ex.getMessage()));
            }
        }, "HarVsJmeter-ReportThread").start();
    }

    private String extractPythonScript() {
        try {
            // Extract bundled Python script from JAR resources to temp file
            InputStream is = getClass().getResourceAsStream("/har_vs_jmeter_core.py");
            if (is == null) {
                log("ERROR: Bundled Python script not found in JAR.");
                return null;
            }
            File tmp = File.createTempFile("har_vs_jmeter_core_", ".py");
            tmp.deleteOnExit();
            Files.copy(is, tmp.toPath(), StandardCopyOption.REPLACE_EXISTING);
            log("Extracted script to: " + tmp.getAbsolutePath());
            return tmp.getAbsolutePath();
        } catch (Exception ex) {
            log("ERROR extracting script: " + ex.getMessage());
            return null;
        }
    }

    private void openInBrowser(String path) {
        try {
            Desktop.getDesktop().browse(new File(path).toURI());
        } catch (Exception ex) {
            log("Could not auto-open browser: " + ex.getMessage());
        }
    }

    // ─────────────────────────────────────────────────────────
    // UI
    // ─────────────────────────────────────────────────────────

    private void init() {
        setLayout(new BorderLayout(0, 8));
        setBorder(new EmptyBorder(8, 8, 8, 8));

        add(makeTitlePanel(), BorderLayout.NORTH);
        add(makeConfigPanel(), BorderLayout.CENTER);
        add(makeLogPanel(), BorderLayout.SOUTH);

        updateModeUI();
    }

    @Override
    protected JPanel makeTitlePanel() {
        JPanel p = new JPanel(new BorderLayout());
        p.setBorder(new EmptyBorder(0, 0, 8, 0));

        JLabel title = new JLabel("HAR vs JMeter Listener");
        title.setFont(title.getFont().deriveFont(Font.BOLD, 14f));
        p.add(title, BorderLayout.WEST);

        JLabel sub = new JLabel("Compares real browser load time (HAR) with JMeter sampler results");
        sub.setForeground(Color.GRAY);
        sub.setFont(sub.getFont().deriveFont(11f));
        p.add(sub, BorderLayout.SOUTH);

        return p;
    }

    private JPanel makeConfigPanel() {
        JPanel p = new JPanel(new GridBagLayout());
        p.setBorder(BorderFactory.createTitledBorder("Configuration"));
        GridBagConstraints gc = new GridBagConstraints();
        gc.insets = new Insets(4, 6, 4, 6);
        gc.fill = GridBagConstraints.HORIZONTAL;

        int row = 0;

        // Mode toggle
        gc.gridx = 0; gc.gridy = row; gc.weightx = 0;
        p.add(new JLabel("Mode:"), gc);

        JPanel modePanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 12, 0));
        liveModeRadio = new JRadioButton("Live (collect during test run)", true);
        offlineModeRadio = new JRadioButton("Offline (use existing JMeter Summary CSV)", false);
        ButtonGroup modeGroup = new ButtonGroup();
        modeGroup.add(liveModeRadio);
        modeGroup.add(offlineModeRadio);
        modePanel.add(liveModeRadio);
        modePanel.add(offlineModeRadio);

        ActionListener modeListener = e -> updateModeUI();
        liveModeRadio.addActionListener(modeListener);
        offlineModeRadio.addActionListener(modeListener);

        gc.gridx = 1; gc.gridwidth = 2; gc.weightx = 1;
        p.add(modePanel, gc);
        gc.gridwidth = 1;

        // HAR file
        row++;
        gc.gridx = 0; gc.gridy = row; gc.weightx = 0;
        p.add(new JLabel("HAR file:"), gc);
        harFileField = new JTextField(40);
        gc.gridx = 1; gc.weightx = 1;
        p.add(harFileField, gc);
        JButton browseHar = new JButton("Browse…");
        browseHar.addActionListener(e -> browseFile(harFileField, "HAR files", ".har"));
        gc.gridx = 2; gc.weightx = 0;
        p.add(browseHar, gc);

        // JMeter Summary Report CSV (offline mode only)
        row++;
        gc.gridx = 0; gc.gridy = row; gc.weightx = 0;
        csvFileLabel = new JLabel("Summary Report CSV:");
        p.add(csvFileLabel, gc);
        csvFileField = new JTextField(40);
        gc.gridx = 1; gc.weightx = 1;
        p.add(csvFileField, gc);
        csvBrowseBtn = new JButton("Browse…");
        csvBrowseBtn.addActionListener(e -> browseFile(csvFileField, "CSV files", ".csv"));
        gc.gridx = 2; gc.weightx = 0;
        p.add(csvBrowseBtn, gc);

        // Output dir
        row++;
        gc.gridx = 0; gc.gridy = row; gc.weightx = 0;
        p.add(new JLabel("Output folder:"), gc);
        outputDirField = new JTextField(System.getProperty("user.home"), 40);
        gc.gridx = 1; gc.weightx = 1;
        p.add(outputDirField, gc);
        JButton browseOut = new JButton("Browse…");
        browseOut.addActionListener(e -> browseDir(outputDirField));
        gc.gridx = 2; gc.weightx = 0;
        p.add(browseOut, gc);

        // Python path
        row++;
        gc.gridx = 0; gc.gridy = row; gc.weightx = 0;
        p.add(new JLabel("Python executable:"), gc);
        pythonField = new JTextField("python", 40);
        gc.gridx = 1; gc.weightx = 1;
        p.add(pythonField, gc);
        JLabel pyHint = new JLabel("(leave 'python' if on PATH)");
        pyHint.setForeground(Color.GRAY);
        pyHint.setFont(pyHint.getFont().deriveFont(11f));
        gc.gridx = 2; gc.weightx = 0;
        p.add(pyHint, gc);

        // Auto open
        row++;
        gc.gridx = 1; gc.gridy = row;
        autoOpenCheck = new JCheckBox("Auto-open report in browser when test ends", true);
        p.add(autoOpenCheck, gc);

        // Run comparison (offline mode)
        row++;
        gc.gridx = 1; gc.gridy = row; gc.gridwidth = 1; gc.weightx = 0;
        runOfflineBtn = new JButton("Run Comparison Now");
        runOfflineBtn.setToolTipText("Generate the report immediately using the HAR file and CSV above — no test run needed.");
        runOfflineBtn.addActionListener(e -> generateReport());
        p.add(runOfflineBtn, gc);
        gc.weightx = 1;

        // Status
        row++;
        gc.gridx = 0; gc.gridy = row; gc.gridwidth = 3;
        statusLabel = new JLabel("Ready.");
        statusLabel.setForeground(new Color(0, 110, 86));
        statusLabel.setFont(statusLabel.getFont().deriveFont(Font.BOLD, 12f));
        p.add(statusLabel, gc);

        return p;
    }

    private JPanel makeLogPanel() {
        JPanel p = new JPanel(new BorderLayout());
        p.setBorder(BorderFactory.createTitledBorder("Log"));
        p.setPreferredSize(new Dimension(0, 180));

        logArea = new JTextArea();
        logArea.setEditable(false);
        logArea.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 11));
        logArea.setBackground(new Color(30, 30, 30));
        logArea.setForeground(new Color(180, 220, 180));

        JScrollPane scroll = new JScrollPane(logArea);
        p.add(scroll, BorderLayout.CENTER);

        JButton clearBtn = new JButton("Clear log");
        clearBtn.addActionListener(e -> logArea.setText(""));
        p.add(clearBtn, BorderLayout.SOUTH);

        return p;
    }

    private void updateModeUI() {
        boolean offline = offlineModeRadio != null && offlineModeRadio.isSelected();

        csvFileLabel.setVisible(offline);
        csvFileField.setVisible(offline);
        csvBrowseBtn.setVisible(offline);
        runOfflineBtn.setVisible(offline);

        autoOpenCheck.setText(offline
                ? "Open report in browser after comparison"
                : "Auto-open report in browser when test ends");

        statusLabel.setText(offline
                ? "Offline mode — pick a HAR file + JMeter Summary CSV, then click 'Run Comparison Now'."
                : "Live mode — report is generated automatically when the test ends.");
    }

    private void browseFile(JTextField field, String desc, String ext) {
        JFileChooser fc = new JFileChooser();
        fc.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(desc, ext.replace(".", "")));
        if (fc.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
            field.setText(fc.getSelectedFile().getAbsolutePath());
        }
    }

    private void browseDir(JTextField field) {
        JFileChooser fc = new JFileChooser();
        fc.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
        if (fc.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
            field.setText(fc.getSelectedFile().getAbsolutePath());
        }
    }

    private void log(String msg) {
        SwingUtilities.invokeLater(() -> {
            logArea.append("[" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss")) + "] " + msg + "\n");
            logArea.setCaretPosition(logArea.getDocument().getLength());
        });
    }

    // ─────────────────────────────────────────────────────────
    // SAVE / RESTORE CONFIG
    // ─────────────────────────────────────────────────────────

    @Override
    public void modifyTestElement(org.apache.jmeter.testelement.TestElement te) {
        super.configureTestElement(te);
        te.setProperty(HAR_FILE_PATH, harFileField.getText());
        te.setProperty(OUTPUT_DIR, outputDirField.getText());
        te.setProperty(PYTHON_PATH, pythonField.getText());
        te.setProperty(AUTO_OPEN, String.valueOf(autoOpenCheck.isSelected()));
        te.setProperty(MODE, offlineModeRadio.isSelected() ? MODE_OFFLINE : MODE_LIVE);
        te.setProperty(CSV_FILE_PATH, csvFileField.getText());
        te.setProperty(INSTANCE_ID, instanceId);
    }

    @Override
    public void configure(org.apache.jmeter.testelement.TestElement te) {
        super.configure(te);
        harFileField.setText(te.getPropertyAsString(HAR_FILE_PATH));
        outputDirField.setText(te.getPropertyAsString(OUTPUT_DIR, System.getProperty("user.home")));
        pythonField.setText(te.getPropertyAsString(PYTHON_PATH, "python"));
        autoOpenCheck.setSelected(!"false".equals(te.getPropertyAsString(AUTO_OPEN, "true")));
        csvFileField.setText(te.getPropertyAsString(CSV_FILE_PATH));

        boolean offline = MODE_OFFLINE.equals(te.getPropertyAsString(MODE, MODE_LIVE));
        offlineModeRadio.setSelected(offline);
        liveModeRadio.setSelected(!offline);
        updateModeUI();
    }

    @Override
    public org.apache.jmeter.testelement.TestElement createTestElement() {
        HarVsJmeterListenerElement el = new HarVsJmeterListenerElement();
        modifyTestElement(el);
        return el;
    }
}
