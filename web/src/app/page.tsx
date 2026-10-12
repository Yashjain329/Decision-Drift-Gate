'use client';
import { SvgDefs } from '@/components/Icon';
import { NoticeBar, Rail, Topbar } from '@/components/Shell';
import { DdgProvider } from '@/lib/store';
import Overview from '@/views/Overview';
import Decisions from '@/views/Decisions';
import CheckStudio from '@/views/CheckStudio';
import Runs from '@/views/Runs';
import Approvals from '@/views/Approvals';
import Reports from '@/views/Reports';
import Settings from '@/views/Settings';

export default function Page() {
  return (
    <DdgProvider>
      <a className="skip-link" href="#main">Skip to workspace</a>
      <SvgDefs />
      <Topbar />
      <div className="shell">
        <Rail />
        <main id="main" className="main" tabIndex={-1}>
          <NoticeBar />
          <Overview />
          <Decisions />
          <CheckStudio />
          <Runs />
          <Approvals />
          <Reports />
          <Settings />
          <footer className="foot"><span>Decision Drift Gate</span><span>Evidence from pinned local Git revisions</span></footer>
        </main>
      </div>
    </DdgProvider>
  );
}
