<!--
  流水线编辑页（certd 式「阶段 → 任务」可视化 + 内联实时日志）
  =========================================================
  交互设计：
  1. 顶部只放三个动作：保存 / 运行 / 返回。运行会自动先保存，避免「改了没生效」；
  2. 中间是阶段卡片，每个阶段按大类上色（申请=蓝、部署=绿、通知=橙），
     一眼能看出这条流程经过哪些环节；
  3. 任务卡上一次执行结果直接标在卡上（绿/红/黄描边），不用去历史里翻；
  4. 日志内联在阶段列表下方（不用抽屉），运行中可以看到每个任务的进展；
  5. 所有表单字段来自后端元数据，新增插件不用改前端。
-->
<template>
  <div class="certd-pipeline-detail art-full-height g-scope" v-loading="loading">
    <!-- 顶部操作条 -->
    <ElCard class="art-card mb-3" shadow="never">
      <div class="detail-head">
        <div class="detail-head-left">
          <ElButton link @click="goBack">
            <ArtSvgIcon icon="ri:arrow-left-line" />
          </ElButton>
          <div class="detail-title-wrap">
            <div class="detail-title-row">
              <h1 class="detail-title" :class="{ 'is-empty': !form.title }">
                {{ form.title || $t('certd.detail.untitled') }}
              </h1>
              <ElTooltip :content="$t('certd.detail.rename')" placement="top">
                <button type="button" class="title-edit-btn" @click="openTitleDialog('pipeline')">
                  <ArtSvgIcon icon="ri:pencil-line" />
                </button>
              </ElTooltip>
            </div>
            <div class="detail-meta">
              <ElTag v-if="isNew" size="small" type="warning" effect="plain">{{ $t('certd.detail.unsaved') }}</ElTag>
              <ElTag v-else-if="dirty" size="small" type="warning" effect="plain">{{ $t('certd.detail.hasChanges') }}</ElTag>
              <ElTag v-if="detail.running" size="small" type="warning" effect="dark">{{ $t('certd.detail.running') }}</ElTag>
              <ElTag v-if="form.disabled" size="small" type="info" effect="plain">{{ $t('certd.detail.disabled') }}</ElTag>
              <span class="detail-meta-text">
                {{ $t('certd.detail.stageCount', { n: stages.length }) }}<template v-if="offStageCount">{{
                  $t('certd.detail.offStageCount', { n: offStageCount })
                }}</template>
                · {{ $t('certd.detail.taskCountText', { n: taskCount }) }}<template v-if="disabledTaskCount">{{
                  $t('certd.detail.taskOffCount', { n: disabledTaskCount })
                }}</template><template v-if="unlinkedTaskCount">{{
                  $t('certd.detail.taskUnlinkedCount', { n: unlinkedTaskCount })
                }}</template>
              </span>
            </div>
          </div>
        </div>
        <!-- 顶部不再放「日志」和「启用/停用」：
             日志由底部终端 + 阶段/任务的日志入口负责；
             启用状态在「证书流水线」列表的表格里直接开关 -->
        <div class="detail-head-right">
          <!-- 画布 / 列表：画布看「真实流水」（节点 + 连线 + 拖动拼接），列表适合窄屏和逐项核对 -->
          <div class="view-switch" role="tablist" :aria-label="$t('certd.detail.viewSwitch')">
            <button
              type="button"
              role="tab"
              :aria-selected="viewMode === 'canvas'"
              :class="{ 'is-active': viewMode === 'canvas' }"
              @click="viewMode = 'canvas'"
            >
              <ArtSvgIcon icon="ri:flow-chart" />{{ $t('certd.detail.viewCanvas') }}
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="viewMode === 'list'"
              :class="{ 'is-active': viewMode === 'list' }"
              @click="viewMode = 'list'"
            >
              <ArtSvgIcon icon="ri:list-check-2" />{{ $t('certd.detail.viewList') }}
            </button>
          </div>
          <!-- 添加阶段紧挨保存：编辑动作集中在一处，不用滚到画布底部找按钮 -->
          <ElButton @click="addStage">
            <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.detail.addStage') }}
          </ElButton>
          <ElButton :loading="saving" @click="save()">
            <ArtSvgIcon icon="ri:save-3-line" class="mr-1" />{{ $t('certd.detail.save') }}
          </ElButton>
          <ElTooltip
            :content="
              timerEnabled && cron
                ? $t('certd.detail.timerTipOn', { cron })
                : $t('certd.detail.timerTipOff')
            "
          >
            <ElButton @click="scheduleDrawerVisible = true">
              <ArtSvgIcon icon="ri:calendar-schedule-line" class="mr-1" />{{ $t('certd.detail.cronTask') }}
              <span class="btn-badge" :class="{ 'is-muted': !cronSummary }">
                {{ cronSummary || $t('certd.detail.notSet') }}
              </span>
            </ElButton>
          </ElTooltip>
          <ElButton type="primary" :loading="running" :disabled="!stages.length" @click="runAndWatch">
            <ArtSvgIcon icon="ri:play-circle-line" class="mr-1" />{{ $t('certd.detail.saveAndRun') }}
          </ElButton>
        </div>
      </div>
      <div class="detail-remark">
        <ElInput v-model="form.remark" :placeholder="$t('certd.detail.remarkPh')" />
      </div>
    </ElCard>

    <!-- 触发方式与执行设置：改成抽屉，由「定时任务」按钮呼出，别让这么长的配置占满页面 -->
    <ElDrawer
      v-model="scheduleDrawerVisible"
      class="g-scope schedule-drawer"
      :title="$t('certd.detail.scheduleTitle')"
      size="min(760px, 96vw)"
      destroy-on-close
    >
      <div class="drawer-body">
        <!-- ① 定时执行 -->
        <section class="setting-block">
          <header class="setting-title">
            <ArtSvgIcon icon="ri:time-line" />
            <span class="setting-title-text">{{ $t('certd.detail.scheduled') }}</span>
            <span class="setting-title-hint">{{ timerEnabled ? $t('certd.detail.timerOn') : $t('certd.detail.timerOff') }}</span>
            <ElTooltip
              :content="timerEnabled ? $t('certd.detail.timerHintOn') : $t('certd.detail.timerHintOff')"
            >
              <ElSwitch v-model="timerEnabled" size="small" class="setting-title-switch" />
            </ElTooltip>
          </header>

          <div class="setting-grid">
            <span class="setting-label">{{ $t('certd.detail.frequency') }}</span>
            <ElRadioGroup
              v-model="scheduleMode"
              size="small"
              class="setting-radio"
              @change="onScheduleModeChange"
            >
              <ElRadioButton value="daily">{{ $t('certd.detail.daily') }}</ElRadioButton>
              <ElRadioButton value="weekly">{{ $t('certd.detail.weekly') }}</ElRadioButton>
              <ElRadioButton value="monthly">{{ $t('certd.detail.monthly') }}</ElRadioButton>
              <ElRadioButton value="once">{{ $t('certd.detail.specificDate') }}</ElRadioButton>
              <ElRadioButton value="custom">{{ $t('certd.detail.custom') }}</ElRadioButton>
            </ElRadioGroup>

            <template
              v-if="scheduleMode === 'daily' || scheduleMode === 'weekly' || scheduleMode === 'monthly'"
            >
              <span class="setting-label">{{ $t('certd.detail.execTime') }}</span>
              <div class="setting-inline">
                <ElTimePicker
                  v-model="scheduleTime"
                  :placeholder="$t('certd.detail.timePh')"
                  format="HH:mm"
                  value-format="HH:mm"
                  :step="15"
                  :clearable="false"
                  class="setting-time"
                />
                <template v-if="scheduleMode === 'weekly'">
                  <span class="setting-label">{{ $t('certd.detail.weekday') }}</span>
                  <ElSelect v-model="scheduleWeekday" class="schedule-select">
                    <ElOption
                      v-for="item in weekdayOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </ElSelect>
                </template>
                <template v-if="scheduleMode === 'monthly'">
                  <span class="setting-label">{{ $t('certd.detail.date') }}</span>
                  <ElSelect v-model="scheduleDay" class="schedule-select">
                    <ElOption
                      v-for="day in 28"
                      :key="day"
                      :label="$t('certd.detail.dayOfMonth', { n: day })"
                      :value="day"
                    />
                  </ElSelect>
                </template>
              </div>
            </template>

            <template v-else-if="scheduleMode === 'once'">
              <span class="setting-label">{{ $t('certd.detail.execTime') }}</span>
              <ElDatePicker
                v-model="scheduleDate"
                type="datetime"
                :placeholder="$t('certd.detail.dateTimePh')"
                format="YYYY-MM-DD HH:mm"
                :clearable="false"
              />
            </template>

            <template v-else>
              <span class="setting-label">cron</span>
              <ElInput v-model="cron" placeholder="0 3 * * *" class="cron-input" />
            </template>
          </div>

          <!-- 当前计划 + 下次执行，单独一条高亮，避免和编辑器混在一起 -->
          <div class="schedule-summary">
            <span class="summary-item">
              <span class="setting-label">{{ $t('certd.detail.plan') }}</span>
              <code class="cron-badge">{{ cron || $t('certd.detail.notFilled') }}</code>
            </span>
            <span v-if="nextRunText" class="summary-item">
              <ArtSvgIcon icon="ri:calendar-check-line" />
              <span class="setting-label">{{ $t('certd.detail.nextRun', { time: nextRunText }) }}</span>
            </span>
          </div>

          <div class="preset-wrap">
            <span class="setting-label preset-label">{{ $t('certd.detail.presets') }}</span>
            <ElTag
              v-for="preset in CRON_PRESETS"
              :key="preset.value"
              class="preset-tag"
              :type="cron === preset.value ? 'primary' : 'info'"
              effect="light"
              @click="applyPreset(preset.value)"
            >
              {{ $t(preset.labelKey) }}
            </ElTag>
          </div>
          <p class="form-tip">{{ $t('certd.detail.cronHint') }}</p>
        </section>

        <!-- ② Webhook 触发 -->
        <section class="setting-block">
          <header class="setting-title">
            <ArtSvgIcon icon="ri:webhook-line" />
            <span class="setting-title-text">{{ $t('certd.detail.webhookTrigger') }}</span>
            <span class="setting-title-hint">{{ $t('certd.detail.webhookHint') }}</span>
          </header>
          <div class="setting-grid">
            <span class="setting-label">{{ $t('certd.detail.triggerKey') }}</span>
            <div class="setting-inline">
              <ElInput
                v-model="triggerKey"
                :placeholder="$t('certd.detail.keyPh')"
                class="setting-grow"
              />
              <ElButton @click="regenerateKey">{{ $t('certd.detail.regenerate') }}</ElButton>
              <ElButton :disabled="!triggerKey" @click="copyTrigger">{{ $t('certd.detail.copy') }}</ElButton>
            </div>
          </div>
          <p class="form-tip">
            POST <code>/api/pipeline/{{ form.id || ':id' }}/trigger</code>
            <template v-if="false" />
            <code>{ "key": "..." }</code>{{ $t('certd.detail.webhookUsage') }}
          </p>
        </section>

        <!-- ③ 执行历史 -->
        <section class="setting-block">
          <header class="setting-title">
            <ArtSvgIcon icon="ri:history-line" />
            <span class="setting-title-text">{{ $t('certd.detail.runHistory') }}</span>
          </header>
          <div class="setting-grid">
            <span class="setting-label">{{ $t('certd.detail.keepCount') }}</span>
            <div class="setting-inline">
              <ElInputNumber
                v-model="form.keepHistoryCount"
                :min="1"
                :max="200"
                size="small"
                class="setting-count"
              />
              <span class="setting-label">{{ $t('certd.detail.countUnit') }}</span>
              <span class="form-tip inline">{{ $t('certd.detail.keepHint') }}</span>
            </div>
          </div>
        </section>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <span class="form-tip inline">{{ $t('certd.detail.saveReminder') }}</span>
          <ElButton @click="scheduleDrawerVisible = false">{{ $t('certd.detail.close') }}</ElButton>
          <ElButton type="primary" :loading="saving" @click="saveSchedule">{{ $t('certd.detail.save') }}</ElButton>
        </div>
      </template>
    </ElDrawer>

    <!-- 编辑标题：标题本身是纯文本，点旁边的铅笔图标才打开这个弹窗 -->
    <ElDialog
      v-model="titleDialog.visible"
      :title="titleDialog.mode === 'pipeline' ? $t('certd.detail.rename') : $t('certd.detail.renameStage')"
      width="min(440px, 92vw)"
      append-to-body
      destroy-on-close
      @closed="onTitleDialogClosed"
    >
      <ElForm label-position="top" @submit.prevent>
        <ElFormItem
          :label="titleDialog.mode === 'pipeline' ? $t('certd.detail.pipelineName') : $t('certd.detail.stageName')"
        >
          <ElInput
            ref="titleInputRef"
            v-model="titleDialog.value"
            :maxlength="titleDialog.mode === 'pipeline' ? 60 : 40"
            show-word-limit
            clearable
            :placeholder="
              titleDialog.mode === 'pipeline'
                ? $t('certd.detail.pipelineNamePh')
                : $t('certd.detail.stageNamePh')
            "
            @keyup.enter="confirmTitleDialog"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="titleDialog.visible = false">{{ $t('certd.detail.cancel') }}</ElButton>
          <ElButton type="primary" @click="confirmTitleDialog">{{ $t('certd.detail.save') }}</ElButton>
        </div>
      </template>
    </ElDialog>

    <!--
      画布视图：Vue Flow 节点画布（阶段=容器、任务=卡片）。
      拖动卡片调位置、从右侧圆点拖到另一张卡片=拼接执行顺序、双击卡片配置。
    -->
    <PipelineCanvas
      v-if="viewMode === 'canvas'"
      :stages="stages"
      :plugin-of="pluginOf"
      :status-of="canvasStatusOf"
      :stage-state-of="stageStateClass"
      :meta-of="summaryEntries"
      :running="running"
      :any-run-active="anyRunActive"
      :bottom-offset="logDockVisible && !logDockCollapsed ? logDockHeight : 0"
      :layout="canvasLayout"
      @open-task="openTaskDialog"
      @task-log="openTaskLogAt"
      @task-delete="removeTask"
      @task-add="openPicker"
      @stage-run="runStageAt"
      @stage-log="openStageLogAt"
      @stage-rename="openTitleDialog('stage', $event)"
      @stage-delete="removeStage"
      @stage-toggle="toggleStage"
      @connect-task="onCanvasConnect"
      @edge-delete="onEdgeDelete"
      @layout-change="onLayoutChange"
    />

    <!-- 阶段列表：竖向流水，阶段之间用箭头串起来，一眼看出执行顺序 -->
    <div v-else class="stage-flow">
      <template v-for="(stage, stageIndex) in stages" :key="stage.id">
        <div v-if="stageIndex > 0" class="flow-link" aria-hidden="true">
          <span class="flow-link-line"></span>
          <ArtSvgIcon icon="ri:arrow-down-s-line" class="flow-link-icon" />
          <span class="flow-link-line"></span>
        </div>

        <ElCard
          class="art-card stage-card"
          :class="[
            'stage-' + kindOfStage(stage).key,
            stageStateClass(stage),
            { 'is-off': stage.enabled === false },
          ]"
          :style="{ '--stage-color': kindOfStage(stage).color }"
          shadow="never"
        >
          <template #header>
            <div class="stage-head">
              <div class="stage-head-left">
                <span class="stage-index">{{ stageIndex + 1 }}</span>
                <span class="stage-icon">
                  <ArtSvgIcon :icon="kindOfStage(stage).icon" />
                </span>
                <div class="stage-title-wrap">
                  <div class="stage-title-row">
                    <span class="stage-title" :class="{ 'is-empty': !stage.title }">
                      {{ stage.title || $t('certd.detail.untitledStage') }}
                    </span>
                    <ElTooltip :content="$t('certd.detail.renameStage')" placement="top">
                      <button
                        type="button"
                        class="title-edit-btn is-small"
                        @click="openTitleDialog('stage', stageIndex)"
                      >
                        <ArtSvgIcon icon="ri:pencil-line" />
                      </button>
                    </ElTooltip>
                  </div>
                  <div class="stage-sub">
                    <span class="stage-kind">{{ $t(kindOfStage(stage).textKey) }}</span>
                    <span class="stage-sep">·</span>
                    <span>
                      {{ $t('certd.detail.stageTasks', { n: stage.tasks.length }) }}<template
                        v-if="stage.enabled !== false"
                      >
                        <template
                          v-if="stage.tasks.filter((task) => task.enabled === false).length"
                        >
                          {{
                            $t('certd.detail.stageTaskOff', {
                              n: stage.tasks.filter((task) => task.enabled === false).length,
                            })
                          }}</template
                        ><template v-if="stage.tasks.filter((task) => task.linked === false).length">
                          {{
                            $t('certd.detail.stageTaskUnlinked', {
                              n: stage.tasks.filter((task) => task.linked === false).length,
                            })
                          }}</template
                        >
                      </template>
                    </span>
                    <!-- 阶段被关掉时整段都不跑，光看单步计数会以为还有任务在执行 -->
                    <span v-if="stage.enabled === false" class="stage-off-tag">{{ $t('certd.detail.stageDisabled') }}</span>
                    <!-- 停用的阶段不再显示上次执行结果：跟「已停用」并排会出现「已停用 · 上次成功」的自相矛盾 -->
                    <template v-if="stageStateText(stage) && stage.enabled !== false">
                      <span class="stage-sep">·</span>
                      <span :class="'stage-state ' + stageStateClass(stage)">
                        {{ stageStateText(stage) }}
                      </span>
                    </template>
                  </div>
                </div>
              </div>
              <div class="stage-head-right">
                <!-- 阶段启停：关掉后运行时会整段跳过（和画布阶段卡片上的开关是同一个状态） -->
                <ElTooltip
                  :content="
                    stage.enabled === false
                      ? $t('certd.detail.stageOffTipOn')
                      : $t('certd.detail.stageOffTipOff')
                  "
                  placement="top"
                >
                  <span class="stage-switch" @click.stop>
                    <ElSwitch
                      :model-value="stage.enabled !== false"
                      size="small"
                      :loading="stageTogglingId === stage.id"
                      @change="(val: string | number | boolean) => toggleStage(stageIndex, Boolean(val))"
                    />
                  </span>
                </ElTooltip>
                <ElTooltip :content="$t('certd.detail.moveUp')" placement="top">
                  <ElButton link :disabled="stageIndex === 0" @click="moveStage(stageIndex, -1)">
                    <ArtSvgIcon icon="ri:arrow-up-line" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip :content="$t('certd.detail.moveDown')" placement="top">
                  <ElButton
                    link
                    :disabled="stageIndex === stages.length - 1"
                    @click="moveStage(stageIndex, 1)"
                  >
                    <ArtSvgIcon icon="ri:arrow-down-line" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip :content="$t('certd.detail.addTaskHere')" placement="top">
                  <ElButton link type="primary" @click="openPicker(stageIndex)">
                    <ArtSvgIcon icon="ri:add-line" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip
                  :content="
                    isStageRunning(stage) || stage.id === stageRunningId
                      ? $t('certd.detail.stageRunning')
                      : $t('certd.detail.runStage')
                  "
                  placement="top"
                >
                  <ElButton
                    link
                    type="primary"
                    :loading="isStageRunning(stage) || stage.id === stageRunningId"
                    :disabled="!stage.tasks.length || anyRunActive || stage.enabled === false"
                    @click="runStage(stage)"
                  >
                    <ArtSvgIcon icon="ri:play-line" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip :content="$t('certd.detail.stageLog')" placement="top">
                  <ElButton link @click="openStageLog(stage)">
                    <ArtSvgIcon icon="ri:terminal-box-line" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip :content="$t('certd.detail.deleteStage')" placement="top">
                  <ElButton link type="danger" @click="removeStage(stageIndex)">
                    <ArtSvgIcon icon="ri:delete-bin-5-line" />
                  </ElButton>
                </ElTooltip>
              </div>
            </div>
          </template>

          <div class="task-grid" :class="{ 'is-empty': !stage.tasks.length }">
            <div
              v-for="(task, taskIndex) in stage.tasks"
              :key="task.id"
              class="task-card"
              :class="[taskStateClass(task.id), { 'is-disabled': task.enabled === false }]"
              @click="openTaskDialog(stageIndex, taskIndex)"
            >
              <div class="task-head">
                <span class="task-seq">{{ taskIndex + 1 }}</span>
                <!-- 图标兼作「日志入口」：执行中换成带动画的执行者图标，点一下看这个任务的日志 -->
                <ElTooltip
                  :content="
                    isTaskRunning(task.id) ? $t('certd.detail.taskRunningTip') : $t('certd.detail.taskLogTip')
                  "
                  placement="top"
                >
                  <button
                    type="button"
                    class="task-icon"
                    :class="{ 'is-running': isTaskRunning(task.id) }"
                    @click.stop="openTaskLog(stage, task)"
                  >
                    <ArtSvgIcon
                      v-if="isTaskRunning(task.id)"
                      icon="ri:robot-2-line"
                      class="task-icon-exec"
                      :style="{ color: pluginOf(task.type)?.color || 'var(--g-blue)' }"
                    />
                    <BrandAvatar
                      v-else
                      :logo-file="pluginOf(task.type)?.logoFile"
                      :logo="pluginOf(task.type)?.logo"
                      :short="pluginOf(task.type)?.short"
                      :color="pluginOf(task.type)?.color"
                      :name="pluginOf(task.type)?.name || task.type"
                      :size="34"
                    />
                  </button>
                </ElTooltip>
                <div class="task-title-wrap">
                  <span class="task-title">{{ task.title || pluginOf(task.type)?.name }}</span>
                  <span v-if="taskTypeLabel(task)" class="task-type">{{ taskTypeLabel(task) }}</span>
                </div>
                <ElTag
                  v-if="task.enabled === false"
                  type="info"
                  size="small"
                  effect="plain"
                  class="task-state"
                >
                  {{ $t('certd.detail.disabled') }}
                </ElTag>
                <!-- 没连线的步骤不会执行：列表视图也要标出来，和画布上的红字一致 -->
                <ElTag
                  v-else-if="task.linked === false"
                  type="danger"
                  size="small"
                  effect="plain"
                  class="task-state"
                >
                  {{ $t('certd.detail.unlinked') }}
                </ElTag>
                <ElTag
                  v-else-if="taskStatus(task.id)"
                  :type="taskStatus(task.id)!.type"
                  size="small"
                  effect="light"
                  class="task-state"
                >
                  {{ taskStatus(task.id)!.text }}
                </ElTag>
                <!-- 单步开关：关掉后运行时会跳过这一步（立刻落库，不用再点保存） -->
                <ElTooltip
                  :content="
                    task.enabled === false ? $t('certd.detail.taskOffTip') : $t('certd.detail.taskOffTipOn')
                  "
                  placement="top"
                >
                  <span class="task-switch" @click.stop>
                    <ElSwitch
                      :model-value="task.enabled !== false"
                      size="small"
                      :loading="taskTogglingId === task.id"
                      @change="(val: string | number | boolean) => toggleTask(stageIndex, taskIndex, val)"
                    />
                  </span>
                </ElTooltip>
              </div>

              <p v-if="pluginOf(task.type)?.desc" class="task-desc">
                {{ pluginOf(task.type)?.desc }}
              </p>

              <dl v-if="summaryEntries(task).length" class="task-meta">
                <div v-for="item in summaryEntries(task)" :key="item.label" class="task-meta-row">
                  <dt>{{ item.label }}</dt>
                  <dd :title="item.value">{{ item.value }}</dd>
                </div>
              </dl>

              <div class="task-foot">
                <span class="task-foot-hint">{{ $t('certd.detail.clickCardToConfig') }}</span>
                <div class="task-actions" @click.stop>
                  <ElTooltip :content="$t('certd.detail.moveLeft')" placement="top">
                    <ElButton
                      link
                      :disabled="taskIndex === 0"
                      @click="moveTask(stageIndex, taskIndex, -1)"
                    >
                      <ArtSvgIcon icon="ri:arrow-left-s-line" />
                    </ElButton>
                  </ElTooltip>
                  <ElTooltip :content="$t('certd.detail.moveRight')" placement="top">
                    <ElButton
                      link
                      :disabled="taskIndex === stage.tasks.length - 1"
                      @click="moveTask(stageIndex, taskIndex, 1)"
                    >
                      <ArtSvgIcon icon="ri:arrow-right-s-line" />
                    </ElButton>
                  </ElTooltip>
                  <ElTooltip :content="$t('certd.detail.config')" placement="top">
                    <ElButton link @click="openTaskDialog(stageIndex, taskIndex)">
                      <ArtSvgIcon icon="ri:settings-3-line" />
                    </ElButton>
                  </ElTooltip>
                  <ElTooltip :content="$t('certd.detail.deleteTask')" placement="top">
                    <ElButton link type="danger" @click="removeTask(stageIndex, taskIndex)">
                      <ArtSvgIcon icon="ri:delete-bin-5-line" />
                    </ElButton>
                  </ElTooltip>
                </div>
              </div>
            </div>

            <button
              type="button"
              class="task-add"
              :class="{ 'is-limit': stage.tasks.length >= MAX_TASKS_PER_STAGE }"
              :disabled="stage.tasks.length >= MAX_TASKS_PER_STAGE"
              @click="openPicker(stageIndex)"
            >
              <ArtSvgIcon
                :icon="stage.tasks.length >= MAX_TASKS_PER_STAGE ? 'ri:checkbox-circle-line' : 'ri:add-line'"
                class="task-add-icon"
              />
              <span class="task-add-text">
                {{
                  stage.tasks.length >= MAX_TASKS_PER_STAGE
                    ? $t('certd.detail.stageFull', { n: MAX_TASKS_PER_STAGE })
                    : stage.tasks.length
                      ? $t('certd.detail.addTask')
                      : $t('certd.detail.addFirstTask')
                }}
              </span>
              <span v-if="!stage.tasks.length" class="task-add-hint">
                {{ $t('certd.detail.pickTask') }}
              </span>
              <span v-else-if="stage.tasks.length < MAX_TASKS_PER_STAGE" class="task-add-hint">
                {{ $t('certd.detail.stageMaxHint', { n: MAX_TASKS_PER_STAGE }) }}
              </span>
            </button>
          </div>
        </ElCard>
      </template>
    </div>

    <!-- 底部终端是 fixed 覆盖层，这里留一段等高占位，免得最后一张卡片永远压在终端底下
         （画布自己按 bottomOffset 缩高，不需要占位） -->
    <div
      v-if="viewMode === 'list'"
      class="log-dock-spacer"
      :style="{ height: dockSpacerHeight }"
      aria-hidden="true"
    />

    <!--
      底部固定终端：所有日志统一收在这里。
      teleport 到 body 是因为本页容器有 overflow-y:auto、路由切换还带 transform，
      留在原地 position:fixed 会被裁切或被祖先的 transform 变成「跟着滚」。
    -->
    <Teleport to="body">
      <section
        v-if="logDockVisible"
        class="log-dock g-scope"
        :class="{ 'is-collapsed': logDockCollapsed, 'is-live': logRunning }"
        :style="{ left: dockLeft + 'px', height: (logDockCollapsed ? 45 : logDockHeight) + 'px' }"
      >
        <div
          v-if="!logDockCollapsed"
          class="log-dock-resizer"
          :title="$t('certd.detail.resizeDock')"
          @pointerdown="startDockResize"
        />

        <header class="log-dock-head">
          <div class="log-dock-brand">
            <ArtSvgIcon icon="ri:terminal-box-line" />
            <span class="log-dock-brand-text">{{ $t('certd.detail.execLog') }}</span>
            <span class="log-dock-count">{{ $t('certd.detail.lineCount', { n: dockLines.length }) }}</span>
            <ElTag v-if="logRunning" size="small" type="warning" effect="light">{{ $t('certd.detail.running') }}</ElTag>
          </div>

          <div class="log-dock-tabs">
            <button
              type="button"
              class="log-dock-tab"
              :class="{ 'is-active': logScope === 'all' }"
              @click="selectLogScope('all')"
            >
              {{ $t('certd.detail.all') }}
              <span class="log-dock-tab-count">{{ logTotalCount }}</span>
            </button>
            <button
              v-if="preparingLines.length"
              type="button"
              class="log-dock-tab"
              :class="{ 'is-active': logScope === 'prep' }"
              @click="selectLogScope('prep')"
            >
              {{ $t('certd.detail.preparing') }}
              <span class="log-dock-tab-count">{{ preparingLines.length }}</span>
            </button>
            <button
              v-for="(stage, stageIndex) in stages"
              :key="stage.id"
              type="button"
              class="log-dock-tab"
              :class="{ 'is-active': logScope === stage.id, 'is-live': isStageRunning(stage) }"
              :style="{ '--tab-color': kindOfStage(stage).color }"
              @click="selectLogScope(stage.id)"
            >
              <i v-if="isStageRunning(stage)" class="log-dock-dot" />
              <i v-else class="log-dock-tab-dot" />
              {{ $t('certd.detail.stageTaskPrefix', { n: stageIndex + 1 }) }} · {{
                stage.title || $t(kindOfStage(stage).textKey)
              }}
              <span class="log-dock-tab-count">{{ stageLogLines(stage).length }}</span>
            </button>
          </div>

          <div class="log-dock-actions">
            <span v-if="logTaskFilter" class="log-dock-filter">
              {{ $t('certd.detail.onlyThis', { name: logTaskFilter }) }}
              <button type="button" :title="$t('certd.detail.clearTaskFilter')" @click="logTaskFilter = ''">
                <ArtSvgIcon icon="ri:close-line" />
              </button>
            </span>
            <ElButton
              link
              class="log-dock-action-secondary"
              :disabled="!dockLines.length"
              @click="copyDockLog"
            >
              {{ $t('certd.detail.copy') }}
            </ElButton>
            <ElButton
              link
              class="log-dock-action-secondary"
              :disabled="!logTotalCount"
              @click="clearDockLog"
            >
              {{ $t('certd.detail.clear') }}
            </ElButton>
            <ElButton link @click="logDockCollapsed = !logDockCollapsed">
              {{ logDockCollapsed ? $t('certd.detail.expand') : $t('certd.detail.collapse') }}
            </ElButton>
            <ElButton link @click="logDockVisible = false">{{ $t('certd.detail.close') }}</ElButton>
          </div>
        </header>

        <div v-show="!logDockCollapsed" class="log-dock-body">
          <LogTerminal
            :lines="dockLines"
            height="100%"
            :show-header="false"
            :accent="dockAccent"
            :empty-text="$t('certd.detail.emptyLog')"
          />
        </div>
      </section>
    </Teleport>

    <!-- 任务类型选择 -->
    <ElDialog
      v-model="pickerVisible"
      class="g-scope"
      :title="$t('certd.detail.pickTaskTitle')"
      width="min(960px, 94vw)"
      destroy-on-close
    >
      <div class="picker-layout">
        <div class="picker-tabs">
          <div
            v-for="group in pickerGroups"
            :key="group.key"
            class="picker-tab"
            :class="{ 'is-active': pickerGroup === group.key }"
            @click="pickerGroup = group.key"
          >
            <ArtSvgIcon :icon="group.icon" />
            <span>{{ $t(group.nameKey) }}</span>
            <span class="picker-tab-count">{{ group.items.length }}</span>
          </div>
        </div>
        <div class="picker-body">
          <div v-for="section in pickerSections" :key="section.title" class="picker-section">
            <div v-if="section.title" class="picker-section-title">{{ section.title }}</div>
            <div class="picker-grid">
              <div
                v-for="plugin in section.items"
                :key="plugin.type"
                class="picker-item"
                @click="choosePlugin(plugin)"
              >
                <BrandAvatar
                  :logo-file="plugin.logoFile"
                  :logo="plugin.logo"
                  :short="plugin.short"
                  :color="plugin.color"
                  :name="plugin.name"
                  :size="32"
                />
                <div class="picker-item-main">
                  <div class="picker-item-title">{{ plugin.name }}</div>
                  <div class="picker-item-desc">{{ plugin.desc }}</div>
                </div>
              </div>
            </div>
          </div>
          <ElEmpty v-if="!pickerSections.length" :description="$t('certd.detail.pickEmpty')" />
        </div>
      </div>
    </ElDialog>

    <!-- 任务配置 -->
    <ElDrawer
      v-model="taskVisible"
      class="g-scope"
      :title="taskDialogTitle"
      size="min(760px, 96vw)"
      destroy-on-close
    >
      <div v-if="editingTask" class="task-editor">
        <ElForm label-width="96px" label-position="top">
          <ElFormItem :label="$t('certd.detail.taskNameLabel')">
            <ElInput v-model="editingTask.title" :placeholder="$t('certd.detail.taskNamePh')" />
          </ElFormItem>
          <ElFormItem :label="$t('certd.detail.continueOnError')">
            <div class="flex items-center gap-2">
              <ElSwitch v-model="editingTask.continueOnError" @change="onContinueChange" />
              <span class="form-tip">{{ $t('certd.detail.ignoreErrors') }}</span>
            </div>
          </ElFormItem>
          <!--
            「失败后跳转」= 这一步挂了就去跑指定的那一步，中间的任务跳过。
            与「失败后继续」互斥：既然要跳到别处，就不该再顺着往下走。
          -->
          <ElFormItem :label="$t('certd.detail.onErrorTarget')">
            <ElSelect
              v-model="editingTask.onErrorTaskId"
              class="w-full"
              clearable
              filterable
              :placeholder="$t('certd.detail.noJumpPh')"
              :disabled="editingTask.continueOnError"
              @change="onErrorTargetChange"
            >
              <ElOption
                v-for="item in errorTargetOptions"
                :key="item.id"
                :label="item.label"
                :value="item.id"
              />
            </ElSelect>
            <p class="field-tip">{{ $t('certd.detail.onErrorHint') }}</p>
          </ElFormItem>
        </ElForm>
        <ElDivider content-position="left">{{ $t('certd.detail.taskParams') }}</ElDivider>
        <PluginForm
          v-if="editingPlugin"
          v-model="editingTask.input"
          :fields="editingPlugin.inputs"
          :task-type="editingTask.type"
          :span="12"
          :cert-domains="certDomains"
        />
        <p v-if="outputKeys.length" class="form-tip mt-2">
          {{ $t('certd.detail.outputVars', { list: outputKeys.join('、') }) }}
        </p>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="taskVisible = false">{{ $t('certd.detail.cancel') }}</ElButton>
          <ElButton type="primary" @click="confirmTask">{{ $t('certd.detail.confirm') }}</ElButton>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import {
    createPipeline,
    fetchAccessOptions,
    fetchPipelineDetail,
    genTriggerKey,
    runPipeline,
    runStagePipeline,
    stopHistory,
    updatePipeline,
  } from '@/api/certd'
  import type { PipelineStage, PipelineTask, TaskPlugin } from '@/api/certd'
  import { usePluginStore } from '@/store/modules/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import {
    CRON_PRESETS,
    STAGE_KIND_META,
    matchShowWhen,
    runStatusMeta,
    shortId,
    stageKindOf,
    type StatusMeta,
  } from '@/utils/certd'
  import BrandAvatar from '../components/brand-avatar.vue'
  import PluginForm from '../components/plugin-form.vue'
  import LogTerminal from '../components/log-terminal.vue'
  import PipelineCanvas from './components/pipeline-canvas.vue'
  import type { CanvasLayout } from './components/canvas-types'
  import { MAX_TASKS_PER_STAGE } from './components/canvas-types'
  import { useRunLog } from '../composables/use-run-log'
  import { $t, i18n } from '@/locales'

  defineOptions({ name: 'CertdPipelineDetail' })

  const route = useRoute()
  const router = useRouter()
  const pluginStore = usePluginStore()

  const loading = ref(false)
  const saving = ref(false)
  const running = ref(false)
  /** 正在单独执行的阶段 id（阶段卡片上的执行按钮 loading 用） */
  const stageRunningId = ref('')
  const dirty = ref(false)
  const isNew = ref(false)
  const detail = ref<any>({})

  const form = reactive({
    id: 0,
    title: '',
    remark: '',
    disabled: false,
    keepHistoryCount: 20,
    type: 'cert_apply',
  })

  const stages = ref<PipelineStage[]>([])
  /** 阶段外框拖过之后的位置，跟着 content 一起落库（任务卡片自身不允许拖，所以只存阶段） */
  const stageLayout = ref<CanvasLayout>({ stages: {}, tasks: {} })
  const triggers = ref<any[]>([])
  const cron = ref('')
  const timerEnabled = ref(true)
  const triggerKey = ref('')
  const lastRun = ref<Record<string, any>>({})

  /* ---------------- 画布视图 ---------------- */
  /** 默认画布：这是「流水」的本来面目；列表视图留着逐项核对 / 窄屏使用 */
  const viewMode = ref<'canvas' | 'list'>(
    typeof window !== 'undefined' && window.innerWidth < 900 ? 'list' : 'canvas'
  )

  /* ---------------- 定时计划：用日历 / 时间选择器，而不是让人背 cron ---------------- */
  type ScheduleMode = 'daily' | 'weekly' | 'monthly' | 'once' | 'custom'
  /** 存 key 而不是文案：模块顶层取值会在首次 import 时把语言烤死 */
  const WEEKDAY_OPTIONS = [
    { labelKey: 'certd.time.mon', value: 1 },
    { labelKey: 'certd.time.tue', value: 2 },
    { labelKey: 'certd.time.wed', value: 3 },
    { labelKey: 'certd.time.thu', value: 4 },
    { labelKey: 'certd.time.fri', value: 5 },
    { labelKey: 'certd.time.sat', value: 6 },
    { labelKey: 'certd.time.sun', value: 0 },
  ]
  /** 响应式版本：切语言后下拉选项跟着变 */
  const weekdayOptions = computed(() =>
    WEEKDAY_OPTIONS.map((item) => ({ value: item.value, label: $t(item.labelKey) }))
  )
  const scheduleMode = ref<ScheduleMode>('daily')
  /** HH:mm */
  const scheduleTime = ref('03:00')
  const scheduleWeekday = ref(1)
  const scheduleDay = ref(1)
  /** 指定日期时的时间（Date） */
  const scheduleDate = ref<Date | null>(null)

  const pad = (value: number) => String(value).padStart(2, '0')

  /** 由「每天 / 每周 / 每月 / 指定日期」推 cron；自定义模式原样返回 */
  const buildCron = (): string => {
    const [hour, minute] = (scheduleTime.value || '03:00').split(':').map((item) => Number(item) || 0)
    switch (scheduleMode.value) {
      case 'daily':
        return minute + ' ' + hour + ' * * *'
      case 'weekly':
        return minute + ' ' + hour + ' * * ' + scheduleWeekday.value
      case 'monthly':
        return minute + ' ' + hour + ' ' + scheduleDay.value + ' * *'
      case 'once': {
        const date = scheduleDate.value
        if (!date) return cron.value
        return (
          date.getMinutes() + ' ' + date.getHours() + ' ' +
          date.getDate() + ' ' + (date.getMonth() + 1) + ' *'
        )
      }
      default:
        return cron.value
    }
  }

  /** 已知 cron 反推成界面状态（打开已有流水线时用） */
  const parseCron = (value: string) => {
    const text = (value || '').trim()
    if (!text) {
      scheduleMode.value = 'daily'
      return
    }
    const parts = text.split(/\s+/)
    if (parts.length !== 5) {
      scheduleMode.value = 'custom'
      return
    }
    const [minute, hour, day, month, weekday] = parts
    const isNumber = (item: string) => /^\d+$/.test(item)
    if (isNumber(minute) && isNumber(hour) && day === '*' && month === '*' && weekday === '*') {
      scheduleMode.value = 'daily'
      scheduleTime.value = pad(Number(hour)) + ':' + pad(Number(minute))
      return
    }
    if (isNumber(minute) && isNumber(hour) && day === '*' && month === '*' && isNumber(weekday)) {
      scheduleMode.value = 'weekly'
      scheduleTime.value = pad(Number(hour)) + ':' + pad(Number(minute))
      scheduleWeekday.value = Number(weekday)
      return
    }
    if (isNumber(minute) && isNumber(hour) && isNumber(day) && month === '*' && weekday === '*') {
      scheduleMode.value = 'monthly'
      scheduleTime.value = pad(Number(hour)) + ':' + pad(Number(minute))
      scheduleDay.value = Number(day)
      return
    }
    scheduleMode.value = 'custom'
  }

  /**
   * 头部「定时任务」按钮上的一句话：把 cron 说成人话（原始表达式放 tooltip）。
   * 只覆盖界面上能选出来的几种形状，其它原样显示 —— 别让人背符号。
   */
  const cronSummary = computed(() => {
    const text = (cron.value || '').trim()
    if (!timerEnabled.value || !text) return ''
    const parts = text.split(/\s+/)
    if (parts.length !== 5) return text
    const [minute, hour, day, month, weekday] = parts
    if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return text
    const time = pad(+hour) + ':' + pad(+minute)
    if (day === '*' && month === '*' && weekday === '*') return $t('certd.detail.cronDaily', { time })
    if (day === '*' && month === '*' && /^\d+$/.test(weekday)) {
      const label = WEEKDAY_OPTIONS.find((item) => item.value === +weekday)
      return $t('certd.detail.cronWeekly', {
        day: label ? $t(label.labelKey) : $t('certd.detail.cronEveryWeekday', { day: weekday }),
        time,
      })
    }
    if (/^\d+$/.test(day) && month === '*' && weekday === '*') {
      return $t('certd.detail.cronMonthly', { day, time })
    }
    return text
  })

  /** 点常用预设：同时把日历选择器切到对应状态，避免「cron 变了但界面没变」 */
  const applyPreset = (value: string) => {
    cron.value = value
    parseCron(value)
  }

  const onScheduleModeChange = () => {
    if (scheduleMode.value === 'once' && !scheduleDate.value) {
      const next = new Date(Date.now() + 60 * 60 * 1000)
      next.setMinutes(0, 0, 0)
      scheduleDate.value = next
    }
    if (scheduleMode.value !== 'custom') cron.value = buildCron()
  }

  watch(
    [scheduleMode, scheduleTime, scheduleWeekday, scheduleDay, scheduleDate],
    () => {
      if (scheduleMode.value !== 'custom') cron.value = buildCron()
    },
    { deep: true }
  )

  const formatDateTime = (date: Date) =>
    date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
    ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes())

  /** 下次执行时间预览：只覆盖界面上能选出来的几种 cron 形状 */
  const nextRunText = computed(() => {
    const text = (cron.value || '').trim()
    const parts = text.split(/\s+/)
    if (parts.length !== 5) return ''
    const [minute, hour, day, month, weekday] = parts
    if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return ''
    const now = new Date()
    const at = (date: Date) => {
      date.setHours(Number(hour), Number(minute), 0, 0)
      return date
    }
    if (day === '*' && month === '*' && weekday === '*') {
      const target = at(new Date(now))
      if (target.getTime() <= now.getTime()) target.setDate(target.getDate() + 1)
      return formatDateTime(target)
    }
    if (day === '*' && month === '*' && /^\d+$/.test(weekday)) {
      const target = at(new Date(now))
      const diff = (Number(weekday) - target.getDay() + 7) % 7
      target.setDate(target.getDate() + diff)
      if (target.getTime() <= now.getTime()) target.setDate(target.getDate() + 7)
      return formatDateTime(target)
    }
    if (/^\d+$/.test(day) && month === '*' && weekday === '*') {
      const target = at(new Date(now))
      target.setDate(Number(day))
      if (target.getTime() <= now.getTime()) target.setMonth(target.getMonth() + 1, Number(day))
      return formatDateTime(target)
    }
    return $t('certd.detail.cronScheduler')
  })

  const taskCount = computed(() =>
    stages.value.reduce((total, stage) => total + (stage.tasks?.length || 0), 0)
  )

  /** 被整段关掉的阶段数 */
  const offStageCount = computed(
    () => stages.value.filter((stage) => stage.enabled === false).length
  )

  /**
   * 被关掉的步骤数：顶部与阶段标题都要能看出「这些这次不会跑」。
   * 整段停用的阶段，里面的任务一个都不会执行 —— 统一算进「已停用」，
   * 否则顶部会显示「3 个任务（0 步已停用）」，和实际执行对不上。
   */
  const disabledTaskCount = computed(() =>
    stages.value.reduce((total, stage) => {
      const tasks = stage.tasks || []
      if (stage.enabled === false) return total + tasks.length
      return total + tasks.filter((task) => task.enabled === false).length
    }, 0)
  )

  /** 没连线的步骤：画布上没线、运行时跳过，顶部摘要要说清楚，否则「4 个任务」和实际执行对不上。
      停用阶段里的任务已经算进「已停用」，这里不重复计。 */
  const unlinkedTaskCount = computed(() =>
    stages.value.reduce((total, stage) => {
      if (stage.enabled === false) return total
      return total + (stage.tasks || []).filter((task) => task.linked === false).length
    }, 0)
  )

  /**
   * 整条流水线申请的证书域名（来自所有「证书申请」任务的 domains）。
   * 部署任务的「站点名称 / 加速域名」按它自动匹配，用户不用去面板里抄名字。
   */
  const certDomains = computed<string[]>(() => {
    const names: string[] = []
    for (const stage of stages.value) {
      for (const task of stage.tasks || []) {
        if (!task.type?.startsWith('CertApply')) continue
        const raw = task.input?.domains
        const list = Array.isArray(raw)
          ? raw
          : typeof raw === 'string'
            ? raw.split(',')
            : []
        for (const item of list) {
          const name = String(item || '').trim()
          if (name && !names.includes(name)) names.push(name)
        }
      }
    }
    return names
  })

  const pluginOf = (type: string) => pluginStore.pluginOf(type)
  const kindOfStage = (stage: PipelineStage) => STAGE_KIND_META[stageKindOf(stage)]

  const taskStatus = (taskId: string): StatusMeta | null => {
    const item = lastRun.value?.[taskId]
    if (!item) return null
    return runStatusMeta(item.status)
  }

  /**
   * 画布节点上的状态徽标。
   * key 直接用后端状态值（success / failed / running / skipped），画布那边拼成 is-xxx 类名。
   */
  const canvasStatusOf = (taskId: string): { key: string; text: string } | null => {
    const status = lastRun.value?.[taskId]?.status
    if (!status) return null
    return { key: String(status), text: runStatusMeta(status).text }
  }

  /** 阶段整体状态：全成功=绿、有失败=红、在跑=黄（四条边，不是只描左边） */
  const stageStateClass = (stage: PipelineStage): string => {
    // 跳过 / 停用 / 未连线的步骤不参与阶段成败判断：证书没到期跳过申请，不代表这个阶段失败
    const states = (stage.tasks || [])
      .map((task) => lastRun.value?.[task.id]?.status)
      .filter((state) => state && state !== 'skipped' && state !== 'disabled' && state !== 'unlinked') as string[]
    if (!states.length) return ''
    if (states.some((state) => state === 'running')) return 'is-running'
    if (states.some((state) => state === 'failed')) return 'is-failed'
    if (states.every((state) => state === 'success')) return 'is-success'
    return ''
  }

  const taskStateClass = (taskId: string): string => {
    const status = lastRun.value?.[taskId]?.status
    if (status === 'failed') return 'is-failed'
    if (status === 'running') return 'is-running'
    if (status === 'success') return 'is-success'
    if (status === 'skipped') return 'is-skipped'
    if (status === 'unlinked') return 'is-skipped'
    return ''
  }

  /** 阶段整体状态文案（配合描边颜色，让「上次跑成什么样」不用去历史里翻） */
  const stageStateText = (stage: PipelineStage): string => {
    const state = stageStateClass(stage)
    if (state === 'is-success') return $t('certd.detail.stateSuccess')
    if (state === 'is-failed') return $t('certd.detail.stateFailed')
    if (state === 'is-running') return $t('certd.detail.stateRunning')
    return ''
  }

  /**
   * 任务会输出哪些变量。
   * 后端 plugins.py 的 outputs 是**字符串数组**（cert.crt / cert.key …），
   * 早先按 { key, name } 对象去取，取不到就 join 出一串「、、、、」。
   * 这里两种结构都认，取不到名字的项直接丢掉，绝不渲染空占位。
   */
  const outputKeys = computed<string[]>(() => {
    const outputs = (editingPlugin.value?.outputs || []) as any[]
    return outputs
      .map((item) => (typeof item === 'string' ? item : item?.key || item?.name || ''))
      .filter((name) => Boolean(String(name || '').trim()))
      .map((name) => String(name).trim())
  })

  /** 授权 id → 授权名（卡片上显示「谷歌EAB」比显示「7」有用得多） */
  const accessOptions = ref<{ id: number; name: string; typeName?: string }[]>([])
  const accessName = (id: any): string => {
    const hit = accessOptions.value.find((item) => String(item.id) === String(id))
    return hit?.name || $t('certd.detail.accessPicked')
  }

  /** 下拉选项文案去掉括注：「Let's Encrypt（免费 DV，90 天）」→「Let's Encrypt」 */
  const optionLabel = (label: string): string => label.replace(/[（(][^）)]*[）)]/g, '').trim() || label

  /**
   * 任务卡副标题：只放「插件类型 + 失败继续」
   * task.title 为空时会回落到插件名，直接渲染会和标题重复成「证书申请 / 证书申请」。
   */
  const taskTypeLabel = (task: PipelineTask): string => {
    const name = pluginOf(task.type)?.name || task.type
    const title = task.title || name
    const parts: string[] = []
    if (title !== name) parts.push(name)
    if (task.continueOnError) parts.push($t('certd.detail.continueOnErrorTag'))
    if (task.onErrorTaskId) parts.push($t('certd.detail.onErrorJumpTag'))
    return parts.join(' · ')
  }

  /** 任务参数摘要：拆成「标签 / 值」两列，卡片里按网格排版，比一串「·」好读 */
  const summaryEntries = (task: PipelineTask): { label: string; value: string }[] => {
    const input = task.input || {}
    const plugin = pluginOf(task.type)
    if (!plugin) return []
    const entries: { label: string; value: string }[] = []

    // 先把「部署到哪」的字段放上来：站点名称 / 加速域名是这条任务最要紧的信息
    for (const field of plugin.inputs || []) {
      if (!field.autoMatchDomains) continue
      const label = String(field.title || field.key).replace(/[（(][^）)]*[）)]/g, '').trim()
      const value = input[field.key]
      const filled = Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== ''
      if (filled) {
        entries.push({ label, value: Array.isArray(value) ? value.join('、') : String(value) })
      } else if (certDomains.value.length) {
        entries.push({ label, value: $t('certd.detail.autoMatchDomains') })
      }
    }

    for (const field of plugin.inputs || []) {
      if (field.autoMatchDomains) continue
      const value = input[field.key]
      if (value === undefined || value === null || value === '') continue
      // 标签里的括注在卡片里只会把标签列撑宽，展示时去掉
      const label = String(field.title || field.key)
        .replace(/[（(][^）)]*[）)]/g, '')
        .trim()
      // 开关类字段是边缘配置，卡片上不占行，进详情看
      if (field.component === 'switch') continue
      if (field.component === 'password') {
        entries.push({ label, value: $t('certd.detail.filled') })
        continue
      }
      if (field.component === 'access') {
        entries.push({ label, value: accessName(value) })
        continue
      }
      if (field.component === 'select' && field.options?.length) {
        const hit = field.options.find((option) => String(option.value) === String(value))
        entries.push({ label, value: hit ? optionLabel(hit.label) : String(value) })
        continue
      }
      if (Array.isArray(value)) {
        if (!value.length) continue
        entries.push({ label, value: value.join('、') })
        continue
      }
      if (typeof value === 'object') continue
      entries.push({ label, value: String(value) })
    }
    return entries.slice(0, 5)
  }

  const markDirty = () => {
    dirty.value = true
  }

  /**
   * 顺序一变（拖线拼接、删阶段、删任务），「失败后跳转」可能指向了不存在的任务，
   * 或者指向了排在自己前面的任务 —— 这两种保存时都会被后端拒。
   * 这里统一扫一遍，把失效的直接断掉，别让用户点保存才看到报错。
   */
  const pruneErrorLinks = () => {
    const flat: string[] = []
    stages.value.forEach((stage) => (stage.tasks || []).forEach((task) => flat.push(task.id)))
    const pos = new Map(flat.map((id, index) => [id, index]))
    let cleared = 0
    for (const stage of stages.value) {
      for (const task of stage.tasks || []) {
        const target = task.onErrorTaskId
        if (!target) continue
        const targetAt = pos.get(target)
        const selfAt = pos.get(task.id) ?? -1
        if (targetAt === undefined || targetAt <= selfAt) {
          task.onErrorTaskId = ''
          cleared++
        }
      }
    }
    return cleared
  }

  /* ---------------- 标题编辑（弹窗） ---------------- */
  /**
   * 流水线名称 / 阶段名称都不再用输入框直接展示（一眼看过去像表单，容易误改），
   * 改成「纯文本 + 铅笔图标」，点图标弹窗里改，改完自动标记未保存。
   */
  const titleDialog = reactive({
    visible: false,
    mode: 'pipeline' as 'pipeline' | 'stage',
    stageIndex: -1,
    value: '',
    original: '',
  })
  const titleInputRef = ref()

  const openTitleDialog = (mode: 'pipeline' | 'stage', stageIndex = -1) => {
    titleDialog.mode = mode
    titleDialog.stageIndex = stageIndex
    const current = mode === 'pipeline' ? form.title || '' : stages.value[stageIndex]?.title || ''
    titleDialog.value = current
    titleDialog.original = current
    titleDialog.visible = true
    nextTick(() => {
      titleInputRef.value?.focus?.()
    })
  }

  const confirmTitleDialog = () => {
    const value = String(titleDialog.value || '').trim()
    if (!value) {
      ElMessage.warning(
        titleDialog.mode === 'pipeline'
          ? $t('certd.detail.titleRequiredPipeline')
          : $t('certd.detail.titleRequiredStage')
      )
      return
    }
    if (titleDialog.mode === 'pipeline') {
      form.title = value
    } else {
      const stage = stages.value[titleDialog.stageIndex]
      if (!stage) {
        titleDialog.visible = false
        return
      }
      stage.title = value
    }
    if (value !== titleDialog.original) markDirty()
    titleDialog.visible = false
  }

  const onTitleDialogClosed = () => {
    titleDialog.value = ''
    titleDialog.original = ''
    titleDialog.stageIndex = -1
  }

  /* ---------------- 加载 ---------------- */
  /** 授权名缓存：只给任务卡摘要用，失败不影响主流程 */
  const loadAccessOptions = async () => {
    try {
      accessOptions.value = (await fetchAccessOptions()) || []
    } catch {
      accessOptions.value = []
    }
  }

  const load = async () => {
    loading.value = true
    try {
      await pluginStore.ensureLoaded()
      loadAccessOptions()
      const id = Number(route.params.id || 0)
      if (!id) {
        // 空白新建
        isNew.value = true
        form.title = $t('certd.detail.newPipelineTitle')
        stages.value = []
        return
      }
      const data = await fetchPipelineDetail(id)
      detail.value = data
      form.id = data.id
      form.title = data.title
      form.remark = data.remark
      form.disabled = data.disabled
      form.keepHistoryCount = data.keepHistoryCount
      form.type = data.type || 'cert_apply'
      stages.value = data.content?.stages ? JSON.parse(JSON.stringify(data.content.stages)) : []
      triggers.value = data.content?.triggers ? JSON.parse(JSON.stringify(data.content.triggers)) : []
      triggerKey.value = data.content?.triggerKey || ''
      // 阶段外框拖过之后的位置（content.layout），没有就按自动布局排
      stageLayout.value = data.content?.layout
        ? JSON.parse(JSON.stringify(data.content.layout))
        : { stages: {}, tasks: {} }
      lastRun.value = data.lastRun?.tasks || {}
      // 打开页面就把上次执行的日志接上，底部终端直接有内容可看
      if (data.lastRun?.id) {
        logScope.value = 'all'
        logTaskFilter.value = ''
        openDock()
        void runLog.connect(data.lastRun.id)
      }
      const timer = triggers.value.find((item) => item.type === 'timer')
      cron.value = timer?.cron || ''
      timerEnabled.value = timer?.enabled !== false
      // 把已有 cron 反推成「每天 / 每周 / 每月」，打开页面就能看到日历选择器而不是一串符号
      parseCron(cron.value)
      if (scheduleMode.value === 'once' && cron.value) {
        const parts = cron.value.split(/\s+/)
        if (parts.length === 5 && /^\d+$/.test(parts[2]) && /^\d+$/.test(parts[3])) {
          const date = new Date()
          date.setMonth(Number(parts[3]) - 1, Number(parts[2]))
          date.setHours(Number(parts[1]) || 0, Number(parts[0]) || 0, 0, 0)
          scheduleDate.value = date
        }
      }
      dirty.value = false
    } catch (error: any) {
      ElMessage.error(error?.message || $t('certd.detail.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  /* ---------------- 阶段 / 任务编辑 ---------------- */
  const addStage = () => {
    stages.value.push({ id: shortId('stage'), title: $t('certd.detail.newStageTitle'), tasks: [] })
    markDirty()
  }

  const removeStage = async (index: number) => {
    if (!stages.value[index].tasks.length) {
      stages.value.splice(index, 1)
      pruneErrorLinks()
      markDirty()
      return
    }
    await ElMessageBox.confirm($t('certd.detail.confirmDeleteStage'), $t('certd.detail.deleteStage'), {
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
     
      type: 'warning',
    })
    stages.value.splice(index, 1)
    pruneErrorLinks()
    markDirty()
  }

  const moveStage = (index: number, offset: number) => {
    const target = index + offset
    if (target < 0 || target >= stages.value.length) return
    const list = stages.value
    ;[list[index], list[target]] = [list[target], list[index]]
    markDirty()
  }

  const moveTask = (stageIndex: number, taskIndex: number, offset: number) => {
    const tasks = stages.value[stageIndex].tasks
    const target = taskIndex + offset
    if (target < 0 || target >= tasks.length) return
    ;[tasks[taskIndex], tasks[target]] = [tasks[target], tasks[taskIndex]]
    markDirty()
  }

  /** 单步启停：改了就落库，否则用户以为生效了、实际跑的还是旧的 */
  const taskTogglingId = ref('')
  const toggleTask = async (
    stageIndex: number,
    taskIndex: number,
    value: string | number | boolean
  ) => {
    const task = stages.value[stageIndex]?.tasks?.[taskIndex]
    if (!task) return
    const next = Boolean(value)
    const before = task.enabled !== false
    task.enabled = next
    taskTogglingId.value = task.id
    try {
      const saved = await save(true)
      if (!saved) {
        task.enabled = before
        return
      }
      ElMessage.success(
        next
          ? '已启用「' + (task.title || '该步骤') + '」'
          : '已停用「' + (task.title || '该步骤') + '」，运行时将跳过这一步'
      )
    } finally {
      taskTogglingId.value = ''
    }
  }

  /**
   * 阶段启停：和单步开关同一个套路 —— 改完立刻落库，否则用户以为关掉了、实际跑的还是旧的。
   * 关掉后引擎按 stage.enabled === false 整段跳过（不再逐个关阶段里的任务）。
   */
  const stageTogglingId = ref('')
  const toggleStage = async (stageIndex: number, enabled?: boolean) => {
    const stage = stages.value[stageIndex]
    if (!stage) return
    // 上一次还在落库就别再发一次：画布上的开关没有 loading 态，连点两下会发两个 PUT
    if (stageTogglingId.value === stage.id) return
    const next = typeof enabled === 'boolean' ? enabled : stage.enabled === false
    const before = stage.enabled !== false
    if (next === before) return
    stage.enabled = next
    stageTogglingId.value = stage.id
    try {
      const saved = await save(true)
      if (!saved) {
        stage.enabled = before
        return
      }
      ElMessage.success(
        next
          ? '已启用「' + (stage.title || '该阶段') + '」'
          : '已停用「' + (stage.title || '该阶段') + '」，运行时将整段跳过'
      )
    } finally {
      stageTogglingId.value = ''
    }
  }

  const removeTask = async (stageIndex: number, taskIndex: number) => {
    await ElMessageBox.confirm($t('certd.detail.confirmDeleteTask'), $t('certd.detail.deleteTask'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
    })
    const [removed] = stages.value[stageIndex].tasks.splice(taskIndex, 1)
    // 别的任务可能把它当作「失败后跳转」的目标，删了要顺手断掉，否则画布会留一条指向空气的红线
    if (removed) {
      for (const stage of stages.value) {
        for (const task of stage.tasks || []) {
          if (task.onErrorTaskId === removed.id) task.onErrorTaskId = ''
        }
      }
    }
    markDirty()
  }

  /* ---------------- 任务选择 ---------------- */
  const pickerVisible = ref(false)
  const pickerGroup = ref<'cert' | 'deploy' | 'notify'>('cert')
  const pickerStageIndex = ref(0)

  const pickerGroups = computed(() => [
    {
      key: 'cert' as const,
      nameKey: 'certd.detail.pickerCert',
      icon: 'ri:file-shield-2-line',
      items: pluginStore.pluginsByGroup.cert || [],
    },
    {
      key: 'deploy' as const,
      nameKey: 'certd.detail.pickerDeploy',
      icon: 'ri:rocket-2-line',
      items: pluginStore.pluginsByGroup.deploy || [],
    },
    {
      key: 'notify' as const,
      nameKey: 'certd.detail.pickerNotify',
      icon: 'ri:notification-3-line',
      items: pluginStore.pluginsByGroup.notify || [],
    },
  ])

  /** 部署类按「主机 / 面板 / 集群 / 云 CDN / 对象存储 / 其它」再分块，方便定位 */
  const pickerSections = computed(() => {
    if (pickerGroup.value === 'deploy') {
      return pluginStore.deployByCategory.map((group) => ({
        title: group.category,
        items: group.plugins,
      }))
    }
    const group = pickerGroups.value.find((item) => item.key === pickerGroup.value)
    return group ? [{ title: '', items: group.items }] : []
  })

  const openPicker = (stageIndex: number) => {
    const stage = stages.value[stageIndex]
    if (!stage) return
    // 一个阶段最多 5 个任务：再多卡片就排成一长条，画布缩放后看不清
    if ((stage.tasks || []).length >= MAX_TASKS_PER_STAGE) {
      ElMessage.warning($t('certd.detail.stageMaxWarn', { n: MAX_TASKS_PER_STAGE }))
      return
    }
    pickerStageIndex.value = stageIndex
    pickerVisible.value = true
  }

  const choosePlugin = (plugin: TaskPlugin) => {
    const stage = stages.value[pickerStageIndex.value]
    if (!stage) return
    // 弹窗开着的时候可能已经加满了（多端 / 快速连点），落库前再拦一次
    if ((stage.tasks || []).length >= MAX_TASKS_PER_STAGE) {
      pickerVisible.value = false
      ElMessage.warning($t('certd.detail.stageMaxWarn', { n: MAX_TASKS_PER_STAGE }))
      return
    }
    const task: PipelineTask = {
      id: shortId('task'),
      type: plugin.type,
      title: plugin.name,
      input: defaultsOf(plugin),
      continueOnError: plugin.group === 'deploy' ? true : false,
      enabled: true,
      // 新加的步骤不自动接进执行链：画布上不给它画线，运行时也会跳过。
      // 用户把它拖接到流程上之后才会变 true（见 onCanvasConnect）。
      // 例外：整条流水线还没有任何任务时，这一个就是起点，必须能跑起来。
      linked: stages.value.some((item) => (item.tasks || []).length > 0) ? false : true,
    }
    stage.tasks.push(task)
    pickerVisible.value = false
    markDirty()
    if (task.linked === false) {
      ElMessage.info($t('certd.detail.addedUnlinked'))
    }
    // 直接打开配置，省掉「再点一次」的步骤
    openTaskDialog(pickerStageIndex.value, stage.tasks.length - 1)
  }

  /** 按元数据里的 default 初始化任务参数 */
  const defaultsOf = (plugin: TaskPlugin): Record<string, any> => {
    const input: Record<string, any> = {}
    for (const field of plugin.inputs || []) {
      if (field.default !== undefined) {
        input[field.key] = Array.isArray(field.default) ? [...field.default] : field.default
      } else if (field.component === 'tags') {
        input[field.key] = []
      } else if (field.component === 'switch') {
        input[field.key] = false
      } else {
        input[field.key] = ''
      }
    }
    return input
  }

  /* ---------------- 任务配置抽屉 ---------------- */
  const taskVisible = ref(false)
  const editingStageIndex = ref(0)
  const editingTaskIndex = ref(0)
  const editingTask = ref<PipelineTask | null>(null)
  const editingPlugin = computed(() =>
    editingTask.value ? pluginOf(editingTask.value.type) : undefined
  )
  const taskDialogTitle = computed(() => {
    const plugin = editingPlugin.value
    return plugin ? $t('certd.detail.configPlugin', { name: plugin.name }) : $t('certd.detail.configTask')
  })

  /** 编辑副本，取消时不影响原任务 */
  const taskBackup = ref('')

  /**
   * 「失败后跳转到」的可选目标：只能选排在当前任务**后面**的任务。
   * 执行顺序是把 stages → tasks 拍平后的线性序列，往前跳会成环。
   */
  const errorTargetOptions = computed(() => {
    const flat: { id: string; label: string }[] = []
    stages.value.forEach((stage, stageIndex) => {
      ;(stage.tasks || []).forEach((task) => {
        // 没连线的步骤运行时会被跳过，跳过去等于什么都没做，所以不给它当候选
        if (task.linked === false) return
        flat.push({
          id: task.id,
          label:
            stageIndex +
            1 +
            '. ' +
            (stage.title || $t('certd.detail.untitledStage')) +
            ' / ' +
            (task.title || task.type),
        })
      })
    })
    const currentId = editingTask.value?.id
    const currentAt = flat.findIndex((item) => item.id === currentId)
    return currentAt < 0 ? flat : flat.slice(currentAt + 1)
  })

  // 「失败后继续」和「失败后跳转」互斥：一个说继续往下走，一个说要跳到别处
  const onContinueChange = (value: string | number | boolean) => {
    if (value && editingTask.value) editingTask.value.onErrorTaskId = ''
  }

  const onErrorTargetChange = (value?: string) => {
    if (value && editingTask.value) editingTask.value.continueOnError = false
  }

  const openTaskDialog = (stageIndex: number, taskIndex: number) => {
    editingStageIndex.value = stageIndex
    editingTaskIndex.value = taskIndex
    const task = stages.value[stageIndex]?.tasks[taskIndex]
    if (!task) return
    editingTask.value = JSON.parse(JSON.stringify(task))
    taskBackup.value = JSON.stringify(editingTask.value)
    taskVisible.value = true
  }

  const confirmTask = () => {
    if (!editingTask.value) return
    const task = editingTask.value
    // 必填校验：只校验「当前真正显示出来的」字段。
    // 漏掉 showWhen 判断会误报——CA 选 Let's Encrypt 时，「自定义 ACME」才需要的
    // 「ACME 目录地址」会被当成必填，弹「请填写「ACME 目录地址」」把人卡住。
    const plugin = pluginOf(task.type)
    const missing = (plugin?.inputs || []).find((field) => {
      if (!field.required) return false
      if (!matchShowWhen(field.showWhen, task.input || {})) return false
      const value = task.input?.[field.key]
      return value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)
    })
    if (missing) {
      ElMessage.warning($t('certd.detail.missingField', { name: missing.title }))
      return
    }
    stages.value[editingStageIndex.value].tasks[editingTaskIndex.value] = task
    dirty.value = true
    taskVisible.value = false
  }

  /* ---------------- 保存 / 运行 ---------------- */
  const buildContent = () => {
    const list = stages.value.filter((stage) => (stage.tasks || []).length > 0)
    const triggerList: any[] = []
    if (cron.value && timerEnabled.value) {
      triggerList.push({
        id: triggers.value.find((item) => item.type === 'timer')?.id || shortId('trigger-timer'),
        type: 'timer',
        cron: cron.value,
        enabled: true,
      })
    }
    for (const trigger of triggers.value) {
      if (trigger.type !== 'timer') triggerList.push(trigger)
    }
    return { stages: list, triggers: triggerList, triggerKey: triggerKey.value, layout: stageLayout.value }
  }

  /** 画布拖完阶段外框后回传坐标：只存阶段，任务卡片的相对位置由顺序决定 */
  const canvasLayout = computed<CanvasLayout>(() => stageLayout.value)
  const onLayoutChange = (layout: CanvasLayout) => {
    stageLayout.value = { stages: { ...(layout?.stages || {}) }, tasks: { ...(layout?.tasks || {}) } }
    markDirty()
  }

  /**
   * 点连线删除。
   * 顺序连线：断开的是「目标那一步」，它变成未连线（不执行），任务本身留在原阶段不动。
   * 失败后连线：清掉源任务的 onErrorTaskId，顺序不受影响。
   * 删之前先问一句，并把后果写清楚 —— 断开后这一步就不跑了，不能让人误点。
   */
  const onEdgeDelete = async (payload: {
    sourceTaskId: string
    targetTaskId: string
    kind: 'next' | 'error'
  }) => {
    const { sourceTaskId, targetTaskId, kind } = payload || ({} as any)
    if (!sourceTaskId || !targetTaskId) return
    const locate = (taskId: string) => {
      for (const stage of stages.value) {
        const hit = (stage.tasks || []).find((task) => task.id === taskId)
        if (hit) return hit
      }
      return null
    }
    const sourceTask = locate(sourceTaskId)
    const targetTask = locate(targetTaskId)
    if (!sourceTask || !targetTask) return
    const name = (task: PipelineTask) => task.title || task.type

    if (kind === 'error') {
      try {
        await ElMessageBox.confirm(
          $t('certd.detail.confirmRemoveFailEdge', { from: name(sourceTask), to: name(targetTask) }),
          $t('certd.detail.removeFailEdgeTitle'),
          {
            type: 'warning',
            confirmButtonText: $t('certd.common.delete'),
            cancelButtonText: $t('certd.common.cancel'),
          }
        )
      } catch {
        return
      }
      sourceTask.onErrorTaskId = ''
      markDirty()
      ElMessage.success($t('certd.detail.removedFailEdge'))
      return
    }

    try {
      await ElMessageBox.confirm(
        $t('certd.detail.confirmDisconnect', { name: name(targetTask) }),
        $t('certd.detail.disconnectTitle'),
        {
          type: 'warning',
          confirmButtonText: $t('certd.detail.disconnect'),
          cancelButtonText: $t('certd.common.cancel'),
        }
      )
    } catch {
      return
    }
    targetTask.linked = false
    markDirty()
    ElMessage.success($t('certd.detail.disconnected', { name: name(targetTask) }))
  }

  const save = async (silent = false): Promise<boolean> => {
    if (!form.title.trim()) {
      ElMessage.warning($t('certd.detail.pipelineNameRequired'))
      return false
    }
    if (!stages.value.some((stage) => stage.tasks.length)) {
      ElMessage.warning($t('certd.detail.stageTaskRequired'))
      return false
    }
    saving.value = true
    try {
      const payload = {
        title: form.title.trim(),
        remark: form.remark,
        content: buildContent(),
        keepHistoryCount: form.keepHistoryCount,
        type: form.type,
        disabled: form.disabled,
      }
      if (form.id) {
        await updatePipeline(form.id, payload)
      } else {
        const result = await createPipeline(payload)
        form.id = result.id
        isNew.value = false
        router.replace('/certd/pipeline/detail/' + result.id)
      }
      dirty.value = false
      if (!silent) ElMessage.success($t('certd.detail.saved'))
      return true
    } catch (error: any) {
      ElMessage.error(error?.message || $t('certd.detail.saveFailed'))
      return false
    } finally {
      saving.value = false
    }
  }

  /* ---------------- 日志：统一收在底部固定终端 ---------------- */
  const runLog = useRunLog()
  const scheduleDrawerVisible = ref(false)

  /** 终端是否显示 / 是否收起 / 高度（顶边可拖动） */
  const logDockVisible = ref(false)
  const logDockCollapsed = ref(false)
  const logDockHeight = ref(264)
  /** 终端左边界：跟着侧边栏宽度走，侧边栏展开/收起都要重新量 */
  const dockLeft = ref(0)
  /** 当前看哪一段：'all' | 'prep' | 阶段 id */
  const logScope = ref<string>('all')
  /** 只看某个任务（点任务图标进来时带上） */
  const logTaskFilter = ref('')

  /** 该阶段自己的日志行 */
  const stageLogLines = (stage: PipelineStage): string[] => runLog.stageLines(stage.title)

  /** 第一个阶段标记之前的行（启动、网络探测…） */
  const preparingLines = computed(
    () => runLog.stageLogs.value.find((group) => !group.title)?.lines || []
  )

  const logTotalCount = computed(() => runLog.lines.value.length)

  /** 阶段是否正在执行：SSE 里 status=running 的任务，其 stage 就是该阶段标题 */
  const isStageRunning = (stage: PipelineStage) => runLog.runningStage.value === stage.title

  const logRunning = computed(
    () => runLog.status.value === 'running' || !!runLog.runningStage.value
  )

  /** 有没有任何执行在进行（整条流水线 / 某阶段）：阶段执行按钮此时禁用，避免并发跑 */
  const anyRunActive = computed(
    () => running.value || !!stageRunningId.value || logRunning.value
  )

  const isTaskRunning = (taskId: string) => lastRun.value?.[taskId]?.status === 'running'

  const scopeStage = computed(() =>
    logScope.value === 'all' || logScope.value === 'prep'
      ? null
      : stages.value.find((item) => item.id === logScope.value) || null
  )

  /** 终端里实际显示的行 */
  const dockLines = computed<string[]>(() => {
    if (logTaskFilter.value) {
      return runLog.taskLines(logTaskFilter.value, scopeStage.value?.title || '')
    }
    if (logScope.value === 'all') return runLog.lines.value
    if (logScope.value === 'prep') return preparingLines.value
    return scopeStage.value ? stageLogLines(scopeStage.value) : []
  })

  const dockAccent = computed(() =>
    scopeStage.value ? kindOfStage(scopeStage.value).color : ''
  )

  /** 终端是 fixed 覆盖层，用等高占位把页面撑开，保证能滚到最后一张卡片 */
  const dockSpacerHeight = computed(() => {
    if (!logDockVisible.value) return '0px'
    return (logDockCollapsed.value ? 45 : logDockHeight.value) + 12 + 'px'
  })

  const syncDockLeft = () => {
    const sidebar = document.querySelector('.layout-sidebar')
    dockLeft.value = sidebar ? Math.max(0, Math.round(sidebar.getBoundingClientRect().right)) : 0
  }

  const openDock = () => {
    logDockVisible.value = true
    logDockCollapsed.value = false
    syncDockLeft()
  }

  const toggleDock = () => {
    if (logDockVisible.value) {
      logDockVisible.value = false
      return
    }
    openDock()
  }

  const selectLogScope = (scope: string) => {
    logScope.value = scope
    logTaskFilter.value = ''
    logDockCollapsed.value = false
  }

  const openStageLog = (stage: PipelineStage) => {
    openDock()
    logScope.value = stage.id
    logTaskFilter.value = ''
  }

  const openTaskLog = (stage: PipelineStage, task: PipelineTask) => {
    openDock()
    logScope.value = stage.id
    logTaskFilter.value = task.title || pluginOf(task.type)?.name || task.type
  }

  const copyDockLog = async () => {
    try {
      await navigator.clipboard.writeText(dockLines.value.join('\n'))
      ElMessage.success($t('certd.detail.logCopied'))
    } catch {
      ElMessage.error($t('certd.detail.copyFailed'))
    }
  }

  const clearDockLog = () => {
    runLog.clear()
    logTaskFilter.value = ''
  }

  /** 拖顶边改高度 */
  const startDockResize = (event: PointerEvent) => {
    event.preventDefault()
    const startY = event.clientY
    const startHeight = logDockHeight.value
    const move = (ev: PointerEvent) => {
      const next = startHeight + (startY - ev.clientY)
      logDockHeight.value = Math.min(Math.max(next, 160), Math.round(window.innerHeight * 0.72))
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  // SSE 推送的任务状态同步到卡片上色（lastRun）
  watch(
    () => runLog.tasks.value,
    (tasks) => {
      const map: Record<string, any> = {}
      for (const item of tasks || []) {
        if (item?.taskId) map[item.taskId] = item
      }
      if (Object.keys(map).length) lastRun.value = { ...lastRun.value, ...map }
      if (runLog.status.value && runLog.status.value !== 'running') {
        detail.value.running = false
      }
    },
    { deep: true }
  )

  /** 抽屉里的「保存」：保存后顺手关掉抽屉 */
  const saveSchedule = async () => {
    const ok = await save()
    if (ok) scheduleDrawerVisible.value = false
  }

  const runAndWatch = async () => {
    running.value = true
    try {
      const saved = await save(true)
      if (!saved) return
      const result = await runPipeline(form.id)
      detail.value.running = true
      // 开跑就把底部终端拉起来，并回到「全部」视图
      openDock()
      logScope.value = 'all'
      logTaskFilter.value = ''
      // 接上这次执行的 SSE：日志按阶段分组，底部终端里用标签切换。
      // 不 await —— 这个流要等整条流水线跑完才结束，不能把按钮一直卡在 loading。
      void runLog.connect(result?.historyId || null)
    } catch (error: any) {
      ElMessage.error(error?.message || $t('certd.detail.startFailed'))
    } finally {
      running.value = false
    }
  }

  /**
   * 单独运行某一个阶段：
   * 先静默保存（避免「改了没生效」），再调按阶段运行的接口，
   * 底部终端自动切到该阶段的日志，任务卡只更新本阶段的状态。
   */
  const runStage = async (stage: PipelineStage) => {
    if (stage.enabled === false) {
      ElMessage.warning($t('certd.detail.stageOffCannotRun'))
      return
    }
    if (!stage.tasks?.length) {
      ElMessage.warning($t('certd.detail.stageNoTask'))
      return
    }
    if (anyRunActive.value) return
    stageRunningId.value = stage.id
    try {
      const saved = await save(true)
      if (!saved) return
      const result = await runStagePipeline(form.id, stage.id)
      detail.value.running = true
      // 终端拉起来并直接切到本阶段
      openDock()
      logScope.value = stage.id
      logTaskFilter.value = ''
      // 不 await —— 流要等该阶段跑完才结束
      void runLog.connect(result?.historyId || null)
    } catch (error: any) {
      ElMessage.error(error?.message || $t('certd.detail.startFailed'))
    } finally {
      stageRunningId.value = ''
    }
  }

  /* ---------------- 其它 ---------------- */
  const regenerateKey = async () => {
    const result = await genTriggerKey()
    triggerKey.value = result.key
    dirty.value = true
  }

  const copyTrigger = async () => {
    const api = '/api/pipeline/' + (form.id || ':id') + '/trigger'
    const text = 'curl -X POST ' + location.origin + api + ' -H "Content-Type: application/json" -d \'{"key":"' + triggerKey.value + '"}\''
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success($t('certd.detail.triggerCopied'))
    } catch {
      ElMessage.error($t('certd.detail.copyFailed'))
    }
  }

  const goBack = () => {
    router.push('/certd/pipeline')
  }

  /* ---------------- 画布事件（列表视图的按钮直接调原函数，这里只做下标 → 对象的适配） ---------------- */
  const openTaskLogAt = (stageIndex: number, taskIndex: number) => {
    const stage = stages.value[stageIndex]
    const task = stage?.tasks?.[taskIndex]
    if (stage && task) openTaskLog(stage, task)
  }

  const runStageAt = (stageIndex: number) => {
    const stage = stages.value[stageIndex]
    if (stage) void runStage(stage)
  }

  const openStageLogAt = (stageIndex: number) => {
    const stage = stages.value[stageIndex]
    if (stage) openStageLog(stage)
  }

  /**
   * 连线拼接：把 target 任务挪到 source 任务后面。
   * 执行顺序就是 stages/tasks 的数组顺序，所以「连线」等价于重排，天然不会成环。
   * 同阶段 → 组内换位；跨阶段 → 把任务搬到 source 所在阶段。
   */
  const onCanvasConnect = (payload: {
    sourceTaskId: string
    targetTaskId: string
    kind?: 'reorder' | 'error'
  }) => {
    const { sourceTaskId, targetTaskId, kind } = payload || ({} as any)
    if (!sourceTaskId || !targetTaskId || sourceTaskId === targetTaskId) return

    const locate = (taskId: string): [number, number] => {
      for (let si = 0; si < stages.value.length; si++) {
        const ti = (stages.value[si].tasks || []).findIndex((task) => task.id === taskId)
        if (ti >= 0) return [si, ti]
      }
      return [-1, -1]
    }

    const [sourceStageIndex, sourceTaskIndex] = locate(sourceTaskId)
    const [targetStageIndex, targetTaskIndex] = locate(targetTaskId)
    if (sourceStageIndex < 0 || targetStageIndex < 0) return

    const sourceStage = stages.value[sourceStageIndex]
    const targetStage = stages.value[targetStageIndex]
    const sourceTask = sourceStage.tasks[sourceTaskIndex]
    const targetTask = targetStage.tasks[targetTaskIndex]

    // ---- 红点拖出来的：配「失败后跳转」，不动顺序 ----
    if (kind === 'error') {
      const flatIndex = (si: number, ti: number) => {
        let n = 0
        for (let s = 0; s < si; s++) n += stages.value[s].tasks?.length || 0
        return n + ti
      }
      if (flatIndex(targetStageIndex, targetTaskIndex) <= flatIndex(sourceStageIndex, sourceTaskIndex)) {
        ElMessage.warning($t('certd.detail.jumpOnlyForward'))
        return
      }
      sourceTask.onErrorTaskId = targetTask.id
      markDirty()
      ElMessage.success(
        $t('certd.detail.jumpToast', {
          from: sourceTask.title || sourceTask.type,
          to: targetTask.title || targetTask.type,
        })
      )
      return
    }

    // ---- 蓝点拖出来的：接线（只表达先后，不搬动任务） ----
    // 任务永远留在它自己的阶段里 —— 早先的实现会把目标任务 splice 到源任务的阶段里，
    // 跨阶段一拖阶段就被「合并」掉了，用户的结构被连线破坏。
    // 现在的语义：连线 = 把目标接进执行链；顺序由「阶段顺序 + 阶段内顺序」决定。
    const flatIndexOf = (si: number, ti: number) => {
      let n = 0
      for (let s = 0; s < si; s++) n += stages.value[s].tasks?.length || 0
      return n + ti
    }
    if (
      flatIndexOf(targetStageIndex, targetTaskIndex) <= flatIndexOf(sourceStageIndex, sourceTaskIndex)
    ) {
      ElMessage.warning($t('certd.detail.connectOnlyForward'))
      return
    }

    const wasUnlinked = targetTask.linked === false
    targetTask.linked = true
    // 从新卡片往外拖线同样是「接线」：源也一起激活
    sourceTask.linked = true
    markDirty()
    if (wasUnlinked) {
      ElMessage.success($t('certd.detail.connected', { name: targetTask.title || targetTask.type }))
    } else {
      // 两步本来就在同一条链上：连线是自动画的，再拖一次不会改变顺序
      ElMessage.info($t('certd.detail.alreadyLinked'))
    }
  }

  /* ---------------- 生命周期：底部终端要跟着侧边栏宽度走 ---------------- */
  let dockSidebarObserver: ResizeObserver | null = null

  onMounted(() => {
    void load()
    syncDockLeft()
    window.addEventListener('resize', syncDockLeft)
    // 侧边栏可以手动展开/收起，宽度变了终端左边界要跟着挪
    const sidebar = document.querySelector('.layout-sidebar')
    if (sidebar && typeof ResizeObserver !== 'undefined') {
      dockSidebarObserver = new ResizeObserver(syncDockLeft)
      dockSidebarObserver.observe(sidebar)
    }
  })

  onUnmounted(() => {
    window.removeEventListener('resize', syncDockLeft)
    dockSidebarObserver?.disconnect()
    dockSidebarObserver = null
  })

  onBeforeRouteLeave(async () => {
    if (!dirty.value) return true
    try {
      await ElMessageBox.confirm($t('certd.detail.leaveConfirm'), $t('certd.detail.leaveTitle'), {
        type: 'warning',
        confirmButtonText: $t('certd.detail.leave'),
        cancelButtonText: $t('certd.detail.stay'),
      })
      return true
    } catch {
      return false
    }
  })
</script>

<style scoped>
  /*
   * shadcn/ui 设计语言（AGENTS 6.0）
   * =========================================================
   * 设计令牌在 shadcn-tokens.scss（--g-* 是它的历史别名），这里只消费。
   * 形态要点：卡片 = 白底 + 1px 描边 + 10px 圆角、**不用 hover 抬升阴影**；
   * 分段控件 / chip 用 rounded-md（6px），不再用 Material 的胶囊（100px）；
   * 阴影只有 --shadow-sm / --shadow-md 两档。
   */

  .certd-pipeline-detail {
    /*
     * art-full-height 是「高度固定 + flex 列」的容器，编辑页内容远比一屏高：
     * 不锁 flex-shrink 的话各区块会被压扁（顶部卡片塌成十几像素、底部设置区被裁掉）。
     */
    overflow-x: hidden;
    overflow-y: auto;
    font-family: var(--g-font);
    color: var(--g-text);
  }

  .certd-pipeline-detail > * {
    flex: 0 0 auto;
  }

  /* 页面内的图标按钮：28px 的 ghost icon button（圆角 6px，不做成圆形） */
  .certd-pipeline-detail :deep(.el-button.is-link) {
    width: 28px;
    height: 28px;
    padding: 0;
    border-radius: var(--radius-sm);
  }

  .certd-pipeline-detail :deep(.el-button.is-link:hover) {
    background: var(--g-fill-hover);
  }

  /* 输入框统一走全局标准样式（el-ui.scss：白底 + 1px 描边 + 聚焦主色）。
     这里以前有一套 Google「填充式、无描边」的覆盖，权重比全局规则高，
     结果这一页的输入框全都没有外围描边 —— 已删除，不要再加回来。 */

  /* 占位符别太浅，cron 这种符号串浅到看不见 */
  .certd-pipeline-detail :deep(.el-input__inner::placeholder) {
    color: var(--g-text-3);
  }

  /* ---------------- 顶部操作条 ---------------- */
  .detail-head {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
    justify-content: space-between;
  }

  .detail-head-left {
    display: flex;
    flex: 1 1 320px;
    gap: 4px;
    align-items: flex-start;
    min-width: 0;
  }

  .detail-title-wrap {
    flex: 1;
    min-width: 0;
    padding-top: 2px;
  }

  /* 标题是纯文本：点旁边的铅笔图标改，不再是一眼看上去就能误编辑的输入框 */
  .detail-title-row {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;
  }

  .detail-title {
    max-width: 100%;
    margin: 0;
    overflow: hidden;
    font-size: 19px;
    font-weight: 500;
    line-height: 1.4;
    letter-spacing: 0.1px;
    color: var(--g-text);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .detail-title.is-empty {
    color: var(--g-text-3);
  }

  .title-edit-btn {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    font-size: 14px;
    color: var(--g-text-3);
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--custom-radius);
    transition: color 0.15s, background-color 0.15s, border-color 0.15s;
  }

  .title-edit-btn:hover {
    color: var(--g-blue);
    background: var(--g-fill-hover);
    border-color: var(--g-line);
  }

  .title-edit-btn.is-small {
    width: 20px;
    height: 20px;
    font-size: 12px;
  }

  .detail-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 6px;
  }

  .detail-meta-text {
    font-size: 12.5px;
    color: var(--g-text-2);
  }

  .detail-head-right {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  /* 画布 / 列表切换：shadcn 的 segmented（muted 轨道 + 白底选中有 1px 描边） */
  .view-switch {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 2px;
    padding: 2px;
    background: var(--g-fill);
    border-radius: var(--radius-md);
  }

  .view-switch button {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    height: 28px;
    padding: 0 10px;
    font-family: var(--g-font);
    font-size: 12.5px;
    font-weight: 500;
    color: var(--g-text-2);
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    transition:
      color 0.14s ease,
      background 0.14s ease,
      border-color 0.14s ease;
  }

  .view-switch button:hover {
    color: var(--g-text);
  }

  .view-switch button.is-active {
    color: var(--g-text);
    background: var(--g-surface);
    border-color: var(--g-line);
    box-shadow: var(--shadow-sm);
  }

  /* 按钮角标：日志按钮显示行数、定时任务按钮显示当前 cron；
     没有内容时也显示「暂无 / 未设置」，按钮里不留空白。
     颜色变量都带兜底值 —— 少一个变量定义就会整块「看不见」。 */
  .btn-badge {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    height: 18px;
    margin-left: 6px;
    padding: 0 7px;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 500;
    line-height: 18px;
    color: var(--muted-foreground);
    background: var(--muted);
    border-radius: var(--radius-sm);
    white-space: nowrap;
    opacity: 1;
  }

  /* 没内容时压暗，但仍然要显示出来（虚线框 + 浅字） */
  .btn-badge.is-muted {
    color: var(--muted-foreground);
    background: transparent;
    border: 1px dashed var(--border);
  }

  /* ---------------- 触发方式与执行设置（抽屉） ----------------
   * 排布：三块纵向卡片（定时执行 / Webhook / 执行历史），
   * 每块内部用「标签列 + 控件列」两列网格对齐；
   * 窄屏（<560px）自动降级成单列，标签在上。
   */
  .drawer-body {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding-bottom: 8px;
  }

  .setting-title-switch {
    flex: 0 0 auto;
    margin-left: auto;
  }

  .schedule-drawer .setting-block,
  .drawer-body > .setting-block {
    margin-bottom: 0;
  }

  .detail-remark {
    margin-top: 14px;
  }

  /* 元素变多时的通用保护：按钮 / 开关 / 标签不参与压缩，输入框保底宽度。
     否则一排东西挤在一起时，按钮会被压成十几像素、输入框被压成一条缝。 */
  .detail-head-right :deep(.el-button),
  .detail-head-right :deep(.el-switch),
  .stage-head-right :deep(.el-button),
  .task-actions :deep(.el-button),
  .setting-row :deep(.el-button),
  .setting-footer :deep(.el-button),
  .dialog-footer :deep(.el-button),
  .preset-tag,
  .detail-meta :deep(.el-tag) {
    flex: 0 0 auto;
  }

  .setting-row :deep(.el-input),
  .setting-row :deep(.el-input-number) {
    min-width: 140px;
  }

  .detail-remark :deep(.el-input__inner) {
    font-size: 13px;
    color: var(--g-text-2);
  }

  /* ---------------- 阶段：竖向流水 ---------------- */
  .stage-flow {
    display: flex;
    flex-direction: column;
    margin-top: 16px;
  }

  /* 阶段之间的连接箭头，把「一条流水线」画出来 */
  .flow-link {
    display: flex;
    flex-direction: column;
    gap: 2px;
    align-items: center;
    padding: 2px 0;
  }

  .flow-link-line {
    width: 0;
    height: 8px;
    border-left: 2px dotted var(--g-line);
  }

  .flow-link-icon {
    font-size: 16px;
    color: var(--g-text-3);
  }

  .stage-card {
    position: relative;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .stage-card:hover {
    box-shadow: var(--g-elev-1);
  }

  .stage-card :deep(.el-card__header) {
    padding: 14px 18px;
    background: transparent;
    border-bottom: 1px solid var(--g-line-2);
  }

  .stage-card :deep(.el-card__body) {
    padding: 16px 18px 18px;
  }

  /* 结果状态：整卡描边（四条边），暗色模式下也看得清 */
  .stage-card.is-success {
    border-color: var(--g-green);
  }

  .stage-card.is-failed {
    border-color: var(--g-red);
  }

  .stage-card.is-running {
    border-color: var(--g-amber);
  }

  .stage-head {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  .stage-head-left {
    display: flex;
    flex: 1;
    gap: 10px;
    align-items: center;
    min-width: 0;
  }

  .stage-head-right {
    display: flex;
    flex: 0 0 auto;
    gap: 2px;
    align-items: center;
  }

  /* 操作按钮平时半透明、hover 才实心；但启停开关是「状态指示」，
     不能被父级 opacity 一起压暗 —— 所以透明度只加在按钮上。 */
  .stage-head-right :deep(.el-button) {
    opacity: 0.55;
    transition: opacity 0.2s;
  }

  .stage-card:hover .stage-head-right :deep(.el-button) {
    opacity: 1;
  }

  /* 步骤序号：方形小徽标（shadcn 的 badge 形态），不是 Material 的 stepper 圆点 */
  .stage-index {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    font-size: 12px;
    font-weight: 600;
    color: var(--stage-color, var(--g-blue));
    background: color-mix(in srgb, var(--stage-color, var(--g-blue)) 9%, transparent);
    border-radius: var(--radius-sm);
  }

  .stage-icon {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 20px;
    font-size: 17px;
    color: var(--stage-color, var(--g-blue));
  }

  .stage-title-wrap {
    flex: 1;
    min-width: 0;
  }

  /* 阶段标题同样是纯文本 + 铅笔图标，点开弹窗改 */
  .stage-title-row {
    display: flex;
    gap: 4px;
    align-items: center;
    max-width: 360px;
    min-width: 0;
  }

  .stage-title {
    overflow: hidden;
    font-size: 15px;
    font-weight: 500;
    color: var(--g-text);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .stage-title.is-empty {
    color: var(--g-text-3);
  }

  .stage-sub {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 3px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--g-text-2);
  }

  /* 环节 chip：shadcn badge（rounded-md + 淡色底），不是胶囊 */
  .stage-kind {
    padding: 1px 8px;
    font-weight: 500;
    color: var(--stage-color, var(--g-blue));
    background: color-mix(in srgb, var(--stage-color, var(--g-blue)) 9%, transparent);
    border-radius: var(--radius-sm);
  }

  .stage-sep {
    color: var(--g-sep);
  }

  .stage-state.is-success {
    color: var(--g-green);
  }

  .stage-state.is-failed {
    color: var(--g-red);
  }

  .stage-state.is-running {
    color: var(--g-amber);
  }

  /* 阶段启停开关：开态跟着环节色走（证书蓝 / 部署绿 / 通知黄） */
  .stage-switch {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    margin-right: 4px;
  }

  .stage-switch :deep(.el-switch) {
    --el-switch-on-color: var(--stage-color, var(--g-blue));
  }

  /* 「整段已停用」标记：灰底小字，不抢标题 */
  .stage-off-tag {
    padding: 1px 6px;
    font-size: 11px;
    color: var(--g-text-3);
    background: var(--g-fill-hover);
    border-radius: var(--radius-sm);
  }

  /* 整段停用：卡片降饱和 + 虚线边，和「某一步停用」区分开 */
  .stage-card.is-off {
    background: var(--g-fill);
    border-style: dashed;
  }

  .stage-card.is-off .stage-title {
    color: var(--g-text-3);
  }

  .stage-card.is-off .stage-index {
    color: var(--g-text-3);
    background: var(--g-fill-hover);
  }

  /* 暗色模式：环节色令牌本身已经是提亮后的值（见 shadcn-tokens 的 --stage-*），
     这里不再做二次混色 —— 混 #fff 会把绿/橙冲成近白，反而丢了环节区分 */

  /* ---------------- 任务卡 ---------------- */
  .task-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 14px;
  }

  .task-grid.is-empty {
    grid-template-columns: 1fr;
  }

  .task-card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px 16px;
    cursor: pointer;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    border-radius: var(--radius-lg);
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .task-card:hover {
    /* shadcn 的卡片 hover 只换描边深浅，不做「描边消失 + 浮起阴影」——
       那个效果会让整块内容跟着位移，一屏多张卡一起 hover 时像在抖。 */
    border-color: color-mix(in srgb, var(--g-text) 22%, var(--g-line));
  }

  .task-card.is-success {
    border-color: var(--g-green);
  }

  .task-card.is-failed {
    border-color: var(--g-red);
  }

  .task-card.is-running {
    border-color: var(--g-amber);
  }

  /* 跳过的步骤（证书未到期 / 已存在 / 刚申请过）：信息蓝虚线，别和失败混淆。
     用 --info 而不是 --g-blue：后者已转指 --brand（近黑/近白），跳过会看起来像「停用」。 */
  .task-card.is-skipped {
    border-style: dashed;
    border-color: var(--info);
  }

  /* 停用的步骤：整卡变淡 + 图标去色，一眼看出这次不会执行它 */
  .task-card.is-disabled {
    opacity: 0.62;
    background: var(--g-fill-hover);
    border-style: dashed;
  }

  .task-card.is-disabled .task-icon {
    filter: grayscale(1);
  }

  .task-card.is-disabled:hover {
    opacity: 0.85;
  }

  .task-switch {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
  }

  .task-switch :deep(.el-switch) {
    --el-switch-on-color: var(--g-green);
  }

  .task-head {
    display: flex;
    gap: 10px;
    align-items: center;
    min-width: 0;
  }

  .task-seq {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    font-size: 11px;
    font-weight: 600;
    color: var(--g-text-2);
    background: var(--g-fill-hover);
    border-radius: var(--radius-sm);
  }

  .task-title-wrap {
    flex: 1;
    min-width: 0;
  }

  .task-title {
    display: -webkit-box;
    overflow: hidden;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.45;
    color: var(--g-text);
    word-break: break-word;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  .task-type {
    display: block;
    overflow: hidden;
    font-size: 12px;
    line-height: 1.45;
    color: var(--g-text-2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-state {
    flex: 0 0 auto;
  }

  .task-desc {
    margin: 0;
    overflow: hidden;
    font-size: 12.5px;
    line-height: 1.6;
    color: var(--g-text-2);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  /* 参数区：标签列对齐 + 值列省略号，替代原来一串「·」连成的长句 */
  .task-meta {
    display: grid;
    /* 标签列最多占 96px：既按内容自适应，又不会被长标题撑开去挤值 */
    grid-template-columns: fit-content(96px) minmax(0, 1fr);
    gap: 4px 12px;
    padding: 10px 12px;
    margin: 0;
    font-size: 12px;
    line-height: 1.55;
    background: var(--g-fill);
    border-radius: var(--radius-md);
  }

  .task-meta-row {
    display: contents;
  }

  .task-meta dt {
    /* 标签列不再无限变宽去挤值：太长就自己省略 */
    overflow: hidden;
    font-weight: 500;
    color: var(--g-text-2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 值允许换两行：长域名 / 证书路径 / 备注不用靠省略号硬挤 */
  .task-meta dd {
    display: -webkit-box;
    margin: 0;
    overflow: hidden;
    line-height: 1.5;
    color: var(--g-text);
    /* 用 anywhere 而不是 break-all：优先在空格/逗号处断，实在放不下才在词中断，
       否则 "htmag.cn, *.htmag.cn, htmag.com" 会被切成 "...htmag.co / m" */
    overflow-wrap: anywhere;
    white-space: normal;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  .task-foot {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
    padding-top: 10px;
    border-top: 1px solid var(--g-line-2);
  }

  .task-foot-hint {
    overflow: hidden;
    font-size: 11px;
    color: var(--g-text-3);
    text-overflow: ellipsis;
    white-space: nowrap;
    opacity: 0;
    transition: opacity 0.2s;
  }

  .task-card:hover .task-foot-hint {
    opacity: 1;
  }

  .task-actions {
    display: flex;
    flex: 0 0 auto;
    gap: 0;
    align-items: center;
    /* 0.45 太淡，1280 以下基本看不见；0.6 仍是次要层级但能辨认 */
    opacity: 0.6;
    transition: opacity 0.2s;
  }

  .task-card:hover .task-actions {
    opacity: 1;
  }

  /* 任务网格里的「添加任务」占一格，比藏在右上角的小加号好找 */
  .task-add {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
    justify-content: center;
    min-height: 112px;
    padding: 14px;
    font-family: inherit;
    color: var(--g-text-2);
    cursor: pointer;
    background: transparent;
    border: 1px dashed var(--g-line);
    border-radius: var(--radius-lg);
    transition: all 0.2s;
  }

  .task-add:hover {
    color: var(--g-blue);
    background: var(--g-blue-50);
    border-color: var(--g-blue);
  }

  /* 满 5 个任务：占位卡变灰且不可点，和画布底部的提示条保持一致的语义 */
  .task-add.is-limit,
  .task-add.is-limit:hover {
    color: var(--g-text-3);
    cursor: not-allowed;
    background: var(--g-fill);
    border-color: var(--g-line);
  }

  .task-add-icon {
    font-size: 20px;
  }

  .task-add-text {
    font-size: 13px;
    font-weight: 500;
  }

  .task-add-hint {
    font-size: 11px;
    color: var(--g-text-3);
  }

  /* ---------------- 触发方式与执行设置 ---------------- */
  .card-header {
    font-size: 15px;
    font-weight: 500;
    color: var(--g-text);
  }

  /* 每块设置一张浅底卡片，块之间用间距隔开，不再是一堵文字墙 */
  .setting-block {
    padding: 14px 16px;
    background: var(--g-fill);
    border: 1px solid var(--g-line-2);
    border-radius: var(--radius-lg);
  }

  .setting-title {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;
    font-size: 13px;
    font-weight: 600;
    color: var(--g-text);
  }

  .setting-title-text {
    flex: 0 0 auto;
  }

  .setting-title-hint {
    font-size: 12px;
    font-weight: 400;
    color: var(--g-text-3);
  }

  .setting-title :deep(svg),
  .setting-title .art-svg-icon {
    color: var(--g-text-2);
  }

  /* 标签列固定宽度 + 控件列自适应：多行之间标签天然对齐 */
  .setting-grid {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    gap: 10px 12px;
    align-items: center;
  }

  .setting-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .setting-inline {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    min-width: 0;
  }

  .setting-label {
    flex: 0 0 auto;
    font-size: 13px;
    color: var(--g-text-2);
  }

  /* 频率选择：5 个按钮在窄屏会换行，允许换行并留出行距 */
  .setting-radio {
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .setting-time,
  .setting-count {
    flex: 0 0 auto;
  }

  .setting-grow {
    flex: 1 1 200px;
    min-width: 160px;
  }

  .preset-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 10px;
  }

  .preset-label {
    margin-right: 2px;
    font-size: 12px;
    color: var(--g-text-3);
  }

  .preset-tag {
    padding: 0 10px;
    cursor: pointer;
    border-radius: var(--custom-radius);
  }

  .preset-tag:hover {
    color: var(--g-blue);
    background: var(--g-blue-50);
  }

  .form-tip {
    margin: 8px 0 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--g-text-2);
  }

  .form-tip.inline {
    margin: 0;
  }

  /* 接口地址 / JSON 片段单独成块，不要跟着中文句子一起断行 */
  .form-tip code {
    display: inline-block;
    padding: 1px 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--g-text);
    white-space: nowrap;
    background: var(--g-fill-hover);
    border-radius: var(--radius-sm);
  }

  .cron-input :deep(.el-input__inner) {
    font-family: var(--font-mono);
    font-size: 13px;
    letter-spacing: 1px;
  }

  /* 当前计划 + 下次执行：一条高亮摘要，跟编辑器分开 */
  .schedule-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    align-items: center;
    padding: 8px 10px;
    margin-top: 12px;
    background: var(--g-surface);
    border: 1px solid var(--g-line-2);
    border-radius: var(--custom-radius);
  }

  .summary-item {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
  }

  .summary-item .art-svg-icon {
    color: var(--g-text-3);
  }

  /* 组内控件保底宽度，窄屏也不会被压成一条缝 */
  .setting-grid :deep(.el-input),
  .setting-grid :deep(.el-input-number),
  .setting-grid :deep(.el-date-editor) {
    min-width: 150px;
  }

  .setting-footer {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    padding-top: 14px;
    margin-top: 4px;
    border-top: 1px solid var(--g-line-2);
  }

  /* 抽屉内容窄屏（手机 / 分屏）降级成单列：标签在上，控件占满整行 */
  @media (max-width: 560px) {
    .setting-grid {
      grid-template-columns: 1fr;
      gap: 6px;
    }

    .setting-block {
      padding: 12px;
    }

    .setting-title-switch {
      margin-left: 0;
    }
  }

  /* ---------------- 任务类型选择弹窗 ---------------- */
  .picker-layout {
    display: flex;
    gap: 16px;
    min-height: 380px;
  }

  .picker-tabs {
    display: flex;
    flex: 0 0 156px;
    flex-direction: column;
    gap: 4px;
  }

  .picker-tab {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 8px 10px;
    font-size: 13px;
    font-weight: 500;
    color: var(--g-text-2);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition:
      background 0.15s ease,
      color 0.15s ease;
  }

  .picker-tab:hover {
    background: var(--g-fill-hover);
  }

  .picker-tab.is-active {
    color: var(--g-blue);
    background: var(--g-blue-50);
  }

  .picker-tab-count {
    margin-left: auto;
    font-size: 11px;
    font-weight: 400;
    color: var(--g-text-3);
  }

  .picker-body {
    flex: 1;
    max-height: 60vh;
    overflow: auto;
  }

  .picker-section {
    margin-bottom: 14px;
  }

  .picker-section-title {
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 500;
    color: var(--g-text-2);
    letter-spacing: 0.3px;
  }

  .picker-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 8px;
  }

  .picker-item {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 10px;
    cursor: pointer;
    border: 1px solid var(--g-line);
    border-radius: var(--radius-md);
    transition:
      border-color 0.15s ease,
      background 0.15s ease;
  }

  .picker-item:hover {
    background: var(--g-fill-hover);
    border-color: color-mix(in srgb, var(--g-text) 22%, var(--g-line));
  }

  .picker-item-main {
    min-width: 0;
  }

  .picker-item-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--g-text);
  }

  .picker-item-desc {
    overflow: hidden;
    font-size: 11.5px;
    color: var(--g-text-2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  /* ---------------- 任务图标（执行中变成动画执行者） ---------------- */
  .task-icon {
    position: relative;
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    padding: 0;
    cursor: pointer;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
  }

  .task-icon:hover {
    background: var(--g-fill-hover);
  }

  .task-icon.is-running::after {
    position: absolute;
    inset: -3px;
    content: '';
    border: 2px solid transparent;
    border-top-color: var(--g-blue);
    border-right-color: var(--g-blue);
    border-radius: 50%;
    animation: task-icon-spin 0.9s linear infinite;
  }

  .task-icon-exec {
    font-size: 20px;
    animation: task-icon-pulse 1.1s ease-in-out infinite;
  }

  @keyframes task-icon-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @keyframes task-icon-pulse {
    0%,
    100% {
      opacity: 0.65;
      transform: scale(0.94);
    }

    50% {
      opacity: 1;
      transform: scale(1.06);
    }
  }

  /* ---------------- 底部固定终端（日志统一收口） ---------------- */
  /*
   * 三个硬要求：贴底、层级最高、不跟页面滚。
   * - 贴底 + 不跟随：position: fixed（所以整块 teleport 到 body，避免被祖先的
   *   overflow/transform 影响，路由切换动画就带 transform）；
   * - 层级最高：App.vue 给 ElConfigProvider 设了 :z-index="3000"，弹层都从 3000 起步
   *   再逐个 +1，所以 3000 这个量级压不住弹层。这里直接给 9999。
   *   代价是会盖住弹窗底部按钮，所以下面用 body.el-popup-parent--hidden 把终端收成一条。
   */
  .log-dock {
    position: fixed;
    right: 0;
    bottom: 0;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #0b0e14;
    border-top: 1px solid #1f2430;
    box-shadow: var(--shadow-md);
  }

  /*
   * 有弹窗/抽屉打开时（Element 会给 body 加这个锁滚动类）整块让开：
   * 9999 的层级会盖住弹窗底部的「确定/取消」，收成一条也还是压着 45px，干脆藏起来。
   * 关掉弹窗立刻回来，头部「日志」按钮上的行数仍然在提示。
   */
  body.el-popup-parent--hidden .log-dock {
    display: none !important;
  }

  .log-dock.is-live {
    border-top-color: var(--g-amber);
  }

  /* 顶边拖动条 */
  .log-dock-resizer {
    position: absolute;
    top: -4px;
    right: 0;
    left: 0;
    z-index: 2;
    height: 8px;
    cursor: ns-resize;
  }

  .log-dock-resizer::after {
    position: absolute;
    top: 4px;
    left: 50%;
    width: 46px;
    height: 3px;
    content: '';
    background: #30363f;
    border-radius: 3px;
    transform: translateX(-50%);
  }

  .log-dock-resizer:hover::after {
    background: #4a5260;
  }

  .log-dock-head {
    display: flex;
    flex: 0 0 auto;
    gap: 12px;
    align-items: center;
    height: 44px;
    padding: 0 10px 0 14px;
    background: #11151c;
    border-bottom: 1px solid #1f2430;
  }

  .log-dock-brand {
    display: flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
    font-size: 12.5px;
    color: #c9d1d9;
    white-space: nowrap;
  }

  .log-dock-brand :deep(svg) {
    font-size: 15px;
  }

  .log-dock-brand-text {
    font-weight: 500;
  }

  .log-dock-count {
    font-weight: 400;
    color: #6e7781;
  }

  /* 阶段标签：横向可滚，不换行 */
  .log-dock-tabs {
    display: flex;
    flex: 1 1 auto;
    gap: 4px;
    align-items: center;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .log-dock-tabs::-webkit-scrollbar {
    height: 0;
  }

  .log-dock-tab {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
    height: 26px;
    padding: 0 10px;
    font-family: inherit;
    font-size: 12px;
    color: #9aa4b2;
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    transition:
      background 0.15s,
      color 0.15s;
  }

  .log-dock-tab:hover {
    color: #e6edf3;
    background: #1b212b;
  }

  .log-dock-tab.is-active {
    color: #e6edf3;
    background: #232b37;
    border-color: #303a48;
  }

  /* 阶段色小圆点：切到哪一段一眼能看出来 */
  .log-dock-tab-dot {
    width: 6px;
    height: 6px;
    background: var(--tab-color, #6e7781);
    border-radius: 50%;
  }

  .log-dock-tab-count {
    color: #6e7781;
    font-variant-numeric: tabular-nums;
  }

  .log-dock-tab.is-active .log-dock-tab-count {
    color: #9aa4b2;
  }

  /* 正在跑的阶段：呼吸灯 */
  .log-dock-dot {
    width: 6px;
    height: 6px;
    background: var(--g-amber);
    border-radius: 50%;
    animation: logDockPulse 1.2s ease-in-out infinite;
  }

  @keyframes logDockPulse {
    0%,
    100% {
      opacity: 0.3;
    }

    50% {
      opacity: 1;
    }
  }

  .log-dock-actions {
    display: flex;
    flex: 0 0 auto;
    gap: 2px;
    align-items: center;
  }

  .log-dock-actions :deep(.el-button) {
    height: 26px;
    padding: 0 9px;
    font-size: 12px;
    color: #9aa4b2;
    border-radius: var(--radius-sm);
  }

  .log-dock-actions :deep(.el-button:hover) {
    color: #e6edf3;
    background: #1b212b;
  }

  .log-dock-actions :deep(.el-button.is-disabled) {
    color: #4a5260;
  }

  /* 「只看某个任务」的过滤 chip */
  .log-dock-filter {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    height: 24px;
    padding: 0 4px 0 10px;
    margin-right: 4px;
    font-size: 12px;
    color: #c9d1d9;
    white-space: nowrap;
    background: #232b37;
    border: 1px solid #303a48;
    border-radius: var(--radius-sm);
  }

  .log-dock-filter button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    color: #9aa4b2;
    cursor: pointer;
    background: transparent;
    border: 0;
    border-radius: 50%;
  }

  .log-dock-filter button:hover {
    color: #e6edf3;
    background: #303a48;
  }

  .log-dock-body {
    flex: 1 1 auto;
    min-height: 0;
  }

  /* 终端填满整块，去掉自己的圆角和描边，看起来和面板是一体的 */
  .log-dock-body :deep(.log-terminal) {
    height: 100%;
    border: 0;
    border-radius: 0;
  }

  /* height 由 flex 决定，别让终端内部的 height:100% 把内容顶出去 */
  .log-dock-body :deep(.log-terminal-body) {
    height: auto !important;
    min-height: 0;
  }

  /* 底部终端的等高占位：保证页面能滚到最后一张卡片 */
  .log-dock-spacer {
    flex: 0 0 auto;
    transition: height 0.18s ease;
  }

  /* 窄屏：让出位置给阶段标签，否则标签会被操作按钮挤没 */
  @media only screen and (width <= 720px) {
    .log-dock-head {
      gap: 8px;
      padding: 0 6px 0 10px;
    }

    .log-dock-brand-text,
    .log-dock-count {
      display: none;
    }

    .log-dock-action-secondary {
      display: none;
    }

    .log-dock-tab {
      padding: 0 8px;
    }
  }

  /* ---------------- 定时计划 ---------------- */
  .schedule-select {
    width: 110px;
    flex: 0 0 auto;
  }

  .cron-badge {
    padding: 1px 8px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--g-text);
    background: var(--g-fill-hover);
    border-radius: var(--radius-sm);
  }

  @media (max-width: 900px) {
    .picker-layout {
      flex-direction: column;
    }

    .picker-tabs {
      flex: 0 0 auto;
      flex-direction: row;
      overflow: auto;
    }

    .picker-tab {
      white-space: nowrap;
    }
  }

  @media (max-width: 600px) {
    .task-grid {
      grid-template-columns: 1fr;
    }

    /* 窄屏：标题占满一行，操作按钮换到下一行右对齐，避免挤成一团 */
    .stage-head-left {
      flex: 1 1 100%;
    }

    .stage-head-right {
      width: 100%;
      justify-content: flex-end;
      opacity: 1;
    }

    .stage-sub .stage-sep,
    .stage-sub .stage-state {
      display: none;
    }

    .task-foot-hint {
      display: none;
    }

    .task-actions {
      opacity: 1;
    }

    .task-meta {
      grid-template-columns: minmax(0, 1fr);
      gap: 2px;
    }
  }
</style>

