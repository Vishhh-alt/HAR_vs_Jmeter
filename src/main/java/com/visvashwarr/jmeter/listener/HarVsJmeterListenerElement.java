package com.visvashwarr.jmeter.listener;

import org.apache.jmeter.engine.util.NoThreadClone;
import org.apache.jmeter.samplers.SampleEvent;
import org.apache.jmeter.samplers.SampleListener;
import org.apache.jmeter.testelement.AbstractTestElement;
import org.apache.jmeter.testelement.TestStateListener;

import java.io.Serializable;

/**
 * TestElement backing class for HarVsJmeterListener.
 *
 * This is the object that actually lives in the running test plan and
 * receives sample results and test lifecycle events from the JMeter engine.
 *
 * IMPORTANT: JMeter builds its execution tree by calling clone() on each
 * TestElement (see JMeterTreeNode.createTestElement() ->
 * AbstractTestElement.clone()). clone() only copies JMeter *properties*
 * (the propMap) — it does NOT copy plain Java fields, even transient ones
 * set via a custom setter. So a direct object reference to the GUI set
 * before clone() would be null on the cloned instance that actually runs.
 *
 * To work around this, the GUI writes a unique instanceId as a TestElement
 * PROPERTY (which DOES survive clone()), and this class looks up the live
 * GUI instance from HarVsJmeterListener.REGISTRY using that ID whenever an
 * engine event fires.
 *
 * NoThreadClone additionally ensures a single shared instance is used
 * across all sampler threads (rather than one clone per thread), so sample
 * results from every thread are collected by the same element.
 */
public class HarVsJmeterListenerElement extends AbstractTestElement
        implements SampleListener, TestStateListener, NoThreadClone, Serializable {

    private static final long serialVersionUID = 1L;

    private HarVsJmeterListener gui() {
        String id = getPropertyAsString(HarVsJmeterListener.INSTANCE_ID);
        if (id == null || id.isEmpty()) {
            return null;
        }
        return HarVsJmeterListener.REGISTRY.get(id);
    }

    // ── SampleListener ──────────────────────────────────────

    @Override
    public void sampleOccurred(SampleEvent e) {
        HarVsJmeterListener gui = gui();
        if (gui != null) {
            gui.add(e.getResult());
        }
    }

    @Override
    public void sampleStarted(SampleEvent e) {
        // no-op
    }

    @Override
    public void sampleStopped(SampleEvent e) {
        // no-op
    }

    // ── TestStateListener ────────────────────────────────────

    @Override
    public void testStarted() {
        HarVsJmeterListener gui = gui();
        if (gui != null) {
            gui.testStarted();
        }
    }

    @Override
    public void testStarted(String host) {
        HarVsJmeterListener gui = gui();
        if (gui != null) {
            gui.testStarted(host);
        }
    }

    @Override
    public void testEnded() {
        HarVsJmeterListener gui = gui();
        if (gui != null) {
            gui.testEnded();
        }
    }

    @Override
    public void testEnded(String host) {
        HarVsJmeterListener gui = gui();
        if (gui != null) {
            gui.testEnded(host);
        }
    }
}
