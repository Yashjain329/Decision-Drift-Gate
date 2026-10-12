'use client';
// PORT TARGET: legacy/index.html section "runs" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function Runs() {
  return (
    <View id="runs" labelledBy="runs-title">
      <PageHead id="runs-title" crumb="Runs & Regressions" title="Run inspector" />
      <Empty glyph="runs">Not ported yet.</Empty>
    </View>
  );
}
