import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Role
from subjects.curriculum_import import (
    CurriculumImportError,
    create_curriculum,
    parse_curriculum_text,
    validate_curriculum,
)

from subjects.forms import StrandForm, SubStrandForm
from subjects.models import Discipline, GradeLevel, Subject


class StrandFormTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_blank_slug_is_generated_from_strand_and_subject_names(self):
        form = StrandForm(data={
            'name': 'Creation',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['slug'],
            'creation-religious-education-grade-1',
        )

    def test_strand_and_substrand_slug_inputs_use_the_standard_form_style(self):
        for form_class in (StrandForm, SubStrandForm):
            with self.subTest(form=form_class.__name__):
                widget = form_class().fields['slug'].widget
                self.assertEqual(widget.attrs.get('class'), 'form-input')
                self.assertEqual(
                    widget.attrs.get('placeholder'),
                    'Leave blank to auto-generate',
                )


class CurriculumImportTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_parse_curriculum_assigns_numbering_from_table_structure(self):
        client = Mock()
        client.chat.return_value = json.dumps([
            {
                'name': '1.0 Creation',
                'sub_strands': ['1.1 Self Awareness', '1.2 My Family'],
            },
            {
                'name': '2.0 The Holy Bible',
                'sub_strands': ['2.1 The Word of God'],
            },
        ])

        curriculum, warnings = parse_curriculum_text(
            '| Strand | Sub-strand |\n| Creation | Self Awareness |',
            self.subject,
            client=client,
        )

        self.assertEqual(curriculum[0]['name'], 'Creation')
        self.assertEqual(curriculum[0]['order'], 1)
        self.assertEqual(curriculum[0]['sub_strands'][0], {
            'name': 'Self Awareness',
            'order': 1,
        })
        self.assertEqual(warnings, [])
        self.assertIn('Religious Education Grade 1', client.chat.call_args.kwargs['user_prompt'])
        self.assertTrue(client.chat.call_args.kwargs['json_mode'])

    def test_invalid_ai_response_is_rejected(self):
        client = Mock()
        client.chat.return_value = 'not json'

        with self.assertRaises(CurriculumImportError):
            parse_curriculum_text('a curriculum table', self.subject, client=client)

    def test_parse_curriculum_accepts_json_object_with_strands(self):
        client = Mock()
        client.chat.return_value = json.dumps({
            'strands': [{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }],
        })

        curriculum, _warnings = parse_curriculum_text(
            'a curriculum table',
            self.subject,
            client=client,
        )

        self.assertEqual(curriculum[0]['name'], 'Creation')
        self.assertEqual(curriculum[0]['sub_strands'][0]['name'], 'Self Awareness')

    def test_validate_curriculum_allows_long_sub_strand_names(self):
        long_name = (
            'Miracles of Jesus Christ (The feeding of the five thousand and other signs)'
        )
        self.assertGreater(len(long_name), 50)
        curriculum, warnings = validate_curriculum([{
            'name': 'The Life of Jesus Christ',
            'sub_strands': [long_name],
        }])
        self.assertEqual(curriculum[0]['sub_strands'][0]['name'], long_name)
        self.assertEqual(warnings, [])

    def test_validate_curriculum_skips_duplicate_sub_strands(self):
        curriculum, warnings = validate_curriculum([{
            'name': 'Numbers',
            'sub_strands': [
                'Whole Numbers',
                'Whole Numbers',
                'Place Value',
            ],
        }])
        self.assertEqual(len(curriculum[0]['sub_strands']), 2)
        self.assertEqual(
            [s['name'] for s in curriculum[0]['sub_strands']],
            ['Whole Numbers', 'Place Value'],
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn('duplicate', warnings[0].casefold())

    def test_create_curriculum_accepts_long_sub_strand_name(self):
        long_name = (
            'Miracles of Jesus Christ (The feeding of the five thousand and other signs)'
        )
        curriculum = [{
            'name': 'The Life of Jesus Christ',
            'order': 1,
            'sub_strands': [{'name': long_name, 'order': 1}],
        }]
        _, created_sub_strands, warnings = create_curriculum(self.subject, curriculum)
        self.assertEqual(created_sub_strands, 1)
        self.assertEqual(warnings, [])
        self.assertTrue(self.subject.strands.filter(sub_strands__name=long_name).exists())

    def test_create_curriculum_creates_strands_and_sub_strands(self):
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [{'name': 'Self Awareness', 'order': 1}],
        }]

        created_strands, created_sub_strands, warnings = create_curriculum(
            self.subject,
            curriculum,
        )

        self.assertEqual((created_strands, created_sub_strands), (1, 1))
        self.assertEqual(warnings, [])
        self.assertEqual(self.subject.strands.get().slug, 'creation-religious-education-grade-1')
        self.assertEqual(
            self.subject.strands.get().sub_strands.get().name,
            'Self Awareness',
        )

    def test_create_curriculum_keeps_existing_entries_and_adds_missing_children(self):
        from subjects.models import Strand, SubStrand

        strand = Strand.objects.create(
            name='Creation',
            order=1,
            slug='creation-existing',
            subject=self.subject,
        )
        SubStrand.objects.create(
            name='Self Awareness',
            order=1,
            slug='self-awareness-existing',
            strand=strand,
        )
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [
                {'name': 'Self Awareness', 'order': 1},
                {'name': 'My Family', 'order': 2},
            ],
        }]

        created_strands, created_sub_strands, warnings = create_curriculum(
            self.subject,
            curriculum,
        )

        self.assertEqual((created_strands, created_sub_strands), (0, 1))
        self.assertEqual(len(warnings), 1)
        self.assertIn('already exists', warnings[0])
        self.assertEqual(self.subject.strands.count(), 1)
        self.assertEqual(strand.sub_strands.count(), 2)

    def test_subject_page_previews_before_importing_and_requires_admin(self):
        user_model = get_user_model()
        admin = user_model.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})
        self.client.force_login(admin)
        with patch('subjects.curriculum_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = json.dumps([{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }])
            response = self.client.post(url, {
                'action': 'parse_curriculum',
                'curriculum_text': 'Creation | Self Awareness',
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review parsed curriculum')
        self.assertContains(response, 'Confirm and create curriculum')
        self.assertEqual(self.subject.strands.count(), 0)

        response = self.client.post(url, {
            'action': 'import_curriculum',
            'preview_token': response.context['curriculum_preview_token'],
        })
        self.assertRedirects(response, url)
        self.assertEqual(self.subject.strands.count(), 1)

    def test_manual_strand_creation_still_works(self):
        admin = get_user_model().objects.create_user(
            phone='0744444446',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        self.client.force_login(admin)
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})

        response = self.client.post(url, {
            'action': 'create_strand',
            'name': 'Creation',
            'slug': '',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertRedirects(response, url)
        self.assertEqual(
            self.subject.strands.get().slug,
            'creation-religious-education-grade-1',
        )

    def test_signed_preview_cannot_be_tampered_with(self):
        from django.core import signing
        from subjects.curriculum_import import PREVIEW_SALT, load_curriculum_preview

        token = signing.dumps([], salt=PREVIEW_SALT)
        with self.assertRaises(CurriculumImportError):
            load_curriculum_preview(token)

    def test_ai_preview_is_hidden_from_non_admins(self):
        user_model = get_user_model()
        teacher = user_model.objects.create_user(
            phone='0744444445',
            password='1234',
            role=Role.TEACHER,
            first_name='Teacher',
            last_name='User',
        )
        self.client.force_login(teacher)
        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {'action': 'parse_curriculum', 'curriculum_text': 'curriculum'},
        )
        self.assertRedirects(response, reverse('core:landing'), fetch_redirect_response=False)
        self.assertEqual(self.subject.strands.count(), 0)


class ObjectivesImportTests(TestCase):
    def setUp(self):
        from subjects.models import Strand, SubStrand

        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1-objectives',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Science',
            slug='science-objectives',
        )
        self.subject = Subject.objects.create(
            name='Science Grade 1',
            slug='science-grade-1-objectives',
            grade_level=grade,
            discipline=discipline,
        )
        self.strand = Strand.objects.create(
            name='Living Things',
            slug='living-things-objectives',
            order=1,
            subject=self.subject,
        )
        self.sub_strand = SubStrand.objects.create(
            name='Classification of Plants',
            slug='classification-of-plants',
            order=1,
            strand=self.strand,
        )
        self.admin = get_user_model().objects.create_user(
            phone='0744444480',
            password='1234',
            role=Role.ADMIN,
            first_name='Obj',
            last_name='Admin',
        )

    def test_validate_objectives_strips_list_markers(self):
        from subjects.objectives_import import (
            SUBSTRAND_OBJECTIVE_NAME_MAX,
            create_sub_strand_objectives,
            validate_objectives,
        )

        objectives, warnings = validate_objectives(
            ['1. Identify local plants', '- Name parts of a plant'],
            max_name_length=SUBSTRAND_OBJECTIVE_NAME_MAX,
        )
        self.assertEqual(warnings, [])
        self.assertEqual(
            [item['name'] for item in objectives],
            ['Identify local plants', 'Name parts of a plant'],
        )

        created, create_warnings = create_sub_strand_objectives(self.sub_strand, objectives)
        self.assertEqual(created, 2)
        self.assertEqual(create_warnings, [])
        self.assertEqual(self.sub_strand.sub_strand_objectives.count(), 2)

    def test_subject_parse_and_import_flow(self):
        from subjects.models import SubStrandObjective

        self.strand.name = 'Living Things and Their Environment'
        self.strand.save()
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})
        self.client.force_login(self.admin)
        ai_payload = json.dumps({
            'sub_strands': [{
                'strand_name': 'Living Things and Their Environment',
                'sub_strand_name': 'Classification of Plants',
                'objectives': ['Classify plants into flowering and non-flowering plants.'],
            }],
        })
        with patch('subjects.objectives_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = ai_payload
            response = self.client.post(url, {
                'action': 'parse_objectives',
                'objectives_text': '1.1 Classification of Plants\n1. Classify plants…',
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review parsed objectives')
        self.assertContains(response, 'Matched')
        self.assertEqual(
            SubStrandObjective.objects.filter(sub_strand=self.sub_strand).count(),
            0,
        )

        response = self.client.post(url, {
            'action': 'import_objectives',
            'preview_token': response.context['objectives_preview_token'],
        })
        self.assertRedirects(response, url)
        self.assertEqual(
            SubStrandObjective.objects.filter(sub_strand=self.sub_strand).count(),
            1,
        )

    def test_kicd_copy_prompts_include_subject_context(self):
        from subjects.curriculum_import import build_kicd_curriculum_copy_prompt
        from subjects.objectives_import import build_kicd_objectives_copy_prompt

        curriculum_prompt = build_kicd_curriculum_copy_prompt(self.subject)
        objectives_prompt = build_kicd_objectives_copy_prompt(self.subject)
        self.assertIn(self.subject.name, curriculum_prompt)
        self.assertIn('"strands"', curriculum_prompt)
        self.assertIn('sub_strands', curriculum_prompt)
        self.assertIn('objectives', curriculum_prompt)
        self.assertNotIn('Do NOT include learning outcomes', curriculum_prompt)
        self.assertIn(self.subject.name, objectives_prompt)
        self.assertIn('kicd.ac.ke', objectives_prompt)
        self.assertIn(self.strand.name, objectives_prompt)
        self.assertIn(self.sub_strand.name, objectives_prompt)
        self.assertIn('Do not ask me to paste', objectives_prompt)
        self.assertNotIn('NO_KICD_TEXT_YET', objectives_prompt)

    def test_match_sub_strand_by_name_only_when_unique(self):
        from subjects.objectives_import import _match_sub_strand

        matched = _match_sub_strand(
            self.subject,
            '',
            'Classification of Plants',
        )
        self.assertEqual(matched, self.sub_strand)


class QuestionActiveToggleTests(TestCase):
    def setUp(self):
        from core.models import Question
        from subjects.models import Discipline, GradeLevel, Strand, SubStrand, Subject

        grade = GradeLevel.objects.create(name='Grade 7', slug='grade-7', level='Junior Secondary')
        discipline = Discipline.objects.create(name='Mathematics', slug='math-toggle')
        self.subject = Subject.objects.create(
            name='Math',
            slug='math-toggle-g7',
            grade_level=grade,
            discipline=discipline,
        )
        strand = Strand.objects.create(
            name='Numbers',
            slug='numbers-toggle',
            subject=self.subject,
        )
        self.sub_strand = SubStrand.objects.create(
            name='Whole Numbers',
            slug='whole-numbers-toggle',
            strand=strand,
        )
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            phone='0744444471',
            password='1234',
            role=Role.ADMIN,
        )
        self.teacher = user_model.objects.create_user(
            phone='0744444472',
            password='1234',
            role=Role.TEACHER,
        )
        self.other_teacher = user_model.objects.create_user(
            phone='0744444473',
            password='1234',
            role=Role.TEACHER,
        )
        self.question = Question.objects.create(
            quiz='Toggle me?',
            difficulty='Easy',
            quiz_type='OpenEnded',
            sub_strand=self.sub_strand,
            is_active=False,
            created_by=self.teacher,
        )
        self.client = Client()
        self.url = reverse('subjects:sub_strand_detail', kwargs={'slug': self.sub_strand.slug})

    def test_admin_can_activate_question(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            {
                'action': 'toggle_question_active',
                'question_uuid': str(self.question.uuid),
            },
        )
        self.assertRedirects(response, self.url)
        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)

    def test_teacher_can_toggle_own_question_only(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            self.url,
            {
                'action': 'toggle_question_active',
                'question_uuid': str(self.question.uuid),
            },
        )
        self.assertRedirects(response, self.url)
        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)

        self.client.force_login(self.other_teacher)
        response = self.client.post(
            self.url,
            {
                'action': 'toggle_question_active',
                'question_uuid': str(self.question.uuid),
            },
        )
        self.assertRedirects(response, self.url)
        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)

    def test_activate_button_shown_to_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, 'Activate')
        self.assertContains(response, 'toggle_question_active')


class CurriculumNameEditingTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 6',
            slug='grade-6',
            level='Upper Primary',
        )
        discipline = Discipline.objects.create(
            name='Agriculture and Nutrition',
            slug='agriculture-and-nutrition',
        )
        self.subject = Subject.objects.create(
            name='Agriculture and Nutrition',
            slug='agriculture-and-nutrition-grade-6',
            grade_level=grade,
            discipline=discipline,
        )
        from subjects.models import Strand, SubStrand

        self.strand = Strand.objects.create(
            name='Crop Production',
            order=1,
            slug='crop-production-agriculture-and-nutrition-grade-6',
            subject=self.subject,
        )
        self.sub_strand = SubStrand.objects.create(
            name='Planting',
            order=1,
            slug='planting-crop-production',
            strand=self.strand,
        )
        self.admin = get_user_model().objects.create_user(
            phone='0744444450',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )

    def test_curriculum_detail_pages_show_name_edit_controls_to_admins(self):
        self.client.force_login(self.admin)
        pages = (
            (
                reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
                'Edit subject',
            ),
            (
                reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug}),
                'Edit Strand Name',
            ),
            (
                reverse('subjects:sub_strand_detail', kwargs={'slug': self.sub_strand.slug}),
                'Edit Sub-strand Name',
            ),
        )

        for url, edit_label in pages:
            with self.subTest(page=edit_label):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, edit_label)

    def test_subject_page_offers_strand_edit_and_delete_actions(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit')
        self.assertContains(response, 'Delete')
        self.assertContains(response, 'action" value="delete_strand')

    def test_admin_can_delete_strand_and_its_dependent_curriculum(self):
        from subjects.models import StrandObjective, SubStrandObjective

        objective = StrandObjective.objects.create(
            name='Identify crops',
            slug='identify-crops',
            strand=self.strand,
        )
        sub_strand_objective = SubStrandObjective.objects.create(
            name='Name local crops',
            slug='name-local-crops',
            sub_strand=self.sub_strand,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {'action': 'delete_strand', 'strand_id': self.strand.pk},
        )

        self.assertRedirects(
            response,
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
        )
        self.assertFalse(type(self.strand).objects.filter(pk=self.strand.pk).exists())
        self.assertFalse(type(self.sub_strand).objects.filter(pk=self.sub_strand.pk).exists())
        self.assertFalse(StrandObjective.objects.filter(pk=objective.pk).exists())
        self.assertFalse(SubStrandObjective.objects.filter(pk=sub_strand_objective.pk).exists())

    def test_delete_strand_cannot_target_another_subject(self):
        from subjects.models import Strand

        other_subject = Subject.objects.create(
            name='Other Subject',
            slug='other-subject-grade-6',
            grade_level=self.subject.grade_level,
            discipline=self.subject.discipline,
        )
        other_strand = Strand.objects.create(
            name='Other Strand',
            order=1,
            slug='other-strand',
            subject=other_subject,
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {'action': 'delete_strand', 'strand_id': other_strand.pk},
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Strand.objects.filter(pk=other_strand.pk).exists())

    def test_admin_can_rename_subject_strand_and_sub_strand_without_changing_slugs(self):
        self.client.force_login(self.admin)
        name_changes = (
            (
                reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
                {
                    'action': 'update_subject',
                    'subject_id': self.subject.pk,
                    'name': 'Agriculture and Nutrition Grade 6',
                    'slug': self.subject.slug,
                    'grade_level': self.subject.grade_level_id,
                    'discipline': self.subject.discipline_id,
                    'is_active': 'on',
                },
                self.subject,
            ),
            (
                reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug}),
                {'action': 'rename_strand', 'name': 'Growing Crops'},
                self.strand,
            ),
            (
                reverse('subjects:sub_strand_detail', kwargs={'slug': self.sub_strand.slug}),
                {'action': 'rename_substrand', 'name': 'Preparing the Soil'},
                self.sub_strand,
            ),
        )

        for url, data, obj in name_changes:
            with self.subTest(model=obj.__class__.__name__):
                old_slug = obj.slug
                response = self.client.post(url, data)
                self.assertRedirects(response, url)
                obj.refresh_from_db()
                self.assertEqual(obj.name, data['name'])
                self.assertEqual(obj.slug, old_slug)

    def test_subject_manage_meta_returns_impact_json(self):
        self.client.force_login(self.admin)
        url = reverse('subjects:subject_manage_meta', kwargs={'slug': self.subject.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['slug'], self.subject.slug)
        self.assertIn('impact', payload)
        strand_row = next(
            (row for row in payload['impact']['rows'] if row['label'] == 'Strands'),
            None,
        )
        self.assertIsNotNone(strand_row)
        self.assertGreaterEqual(strand_row['count'], 1)

    def test_admin_can_delete_subject_with_curriculum(self):
        from subjects.models import Subject

        subject_pk = self.subject.pk
        grade_slug = self.subject.grade_level.slug
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {
                'action': 'delete_subject',
                'subject_id': self.subject.pk,
            },
        )
        self.assertRedirects(
            response,
            reverse('subjects:subject_list') + f'?grade={grade_slug}',
        )
        self.assertFalse(Subject.objects.filter(pk=subject_pk).exists())
        self.assertEqual(self.strand.__class__.objects.filter(pk=self.strand.pk).count(), 0)

    def test_duplicate_names_are_rejected_for_each_curriculum_level(self):
        from subjects.models import Strand, SubStrand

        other_subject = Subject.objects.create(
            name='Existing Subject',
            slug='existing-subject-grade-6',
            grade_level=self.subject.grade_level,
            discipline=self.subject.discipline,
        )
        other_strand = Strand.objects.create(
            name='Existing Strand',
            order=2,
            slug='existing-strand',
            subject=self.subject,
        )
        SubStrand.objects.create(
            name='Existing Sub-strand',
            order=2,
            slug='existing-sub-strand',
            strand=self.strand,
        )
        self.client.force_login(self.admin)

        cases = (
            (
                reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
                {
                    'action': 'update_subject',
                    'subject_id': self.subject.pk,
                    'name': other_subject.name,
                    'slug': self.subject.slug,
                    'grade_level': self.subject.grade_level_id,
                    'discipline': self.subject.discipline_id,
                },
                'subject_edit_form',
                'A subject with this name already exists',
            ),
            (
                reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug}),
                {'action': 'rename_strand', 'name': other_strand.name},
                'strand_name_form',
                'A strand with this name already exists',
            ),
            (
                reverse('subjects:sub_strand_detail', kwargs={'slug': self.sub_strand.slug}),
                {'action': 'rename_substrand', 'name': 'Existing Sub-strand'},
                'sub_strand_name_form',
                'A sub-strand with this name already exists',
            ),
        )
        for url, data, form_name, error in cases:
            with self.subTest(form=form_name):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                self.assertTrue(response.context[form_name].errors)

    def test_non_admin_cannot_rename_strand_or_sub_strand(self):
        teacher = get_user_model().objects.create_user(
            phone='0744444451',
            password='1234',
            role=Role.TEACHER,
            first_name='Teacher',
            last_name='User',
        )
        self.client.force_login(teacher)

        strand_url = reverse('subjects:strand_detail', kwargs={'slug': self.strand.slug})
        response = self.client.post(
            strand_url,
            {'action': 'rename_strand', 'name': 'Unauthorized Strand Name'},
        )
        self.assertRedirects(response, strand_url)
        self.strand.refresh_from_db()
        self.assertEqual(self.strand.name, 'Crop Production')

        sub_strand_url = reverse(
            'subjects:sub_strand_detail',
            kwargs={'slug': self.sub_strand.slug},
        )
        response = self.client.post(
            sub_strand_url,
            {'action': 'rename_substrand', 'name': 'Unauthorized Sub-strand Name'},
        )
        self.assertRedirects(response, sub_strand_url)
        self.sub_strand.refresh_from_db()
        self.assertEqual(self.sub_strand.name, 'Planting')


class SubjectImportTests(TestCase):
    def setUp(self):
        self.grade = GradeLevel.objects.create(
            name='Grade 10',
            slug='grade-10',
            level='Senior Secondary',
        )
        self.disciplines = {
            slug: Discipline.objects.create(name=name, slug=slug)
            for name, slug in (
                ('Technical & Applied', 'technical-applied'),
                ('Creative & Psychomotor', 'creative-psychomotor'),
                ('Language & Communication', 'language-communication'),
                ('Environment & Social', 'environment-social'),
                ('Mathematics & Science', 'mathematics-science'),
                ('Religious & Moral', 'religious-moral'),
            )
        }
        self.admin = get_user_model().objects.create_user(
            phone='0744444452',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )

    def test_grade_subject_parser_previews_then_creates_subjects(self):
        from subjects.models import Subject

        url = reverse('subjects:subject_list') + '?grade=grade-10'
        self.client.force_login(self.admin)
        ai_response = json.dumps({
            'subjects': [
                {'name': 'Applied Sciences', 'discipline': 'Technical & Applied'},
                {'name': 'Arts & Sports', 'discipline': 'Creative & Psychomotor'},
                {'name': 'Foreign Languages', 'discipline': 'Language & Communication'},
                {'name': 'Humanities', 'discipline': 'Environment & Social'},
                {'name': 'Languages', 'discipline': 'Language & Communication'},
                {'name': 'Pure Sciences', 'discipline': 'Mathematics & Science'},
                {'name': 'Religious Education', 'discipline': 'Religious Education'},
                {'name': 'Technical Studies', 'discipline': 'Technical & Applied'},
            ],
        })

        with patch('subjects.subject_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = ai_response
            response = self.client.post(url, {
                'action': 'parse_subjects',
                'subject_text': '## Grade 10 Designs\n\n- [Applied Sciences](https://example.test)',
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['subject_preview']), 8)
        self.assertContains(response, 'Review 8 subjects')
        self.assertEqual(Subject.objects.filter(grade_level=self.grade).count(), 0)

        response = self.client.post(url, {
            'action': 'import_subjects',
            'preview_token': response.context['subject_preview_token'],
        })

        self.assertRedirects(response, url)
        subjects = Subject.objects.filter(grade_level=self.grade)
        self.assertEqual(subjects.count(), 8)
        self.assertEqual(
            subjects.get(name='Applied Sciences').discipline,
            self.disciplines['technical-applied'],
        )
        self.assertEqual(
            subjects.get(name='Religious Education').discipline,
            self.disciplines['religious-moral'],
        )

    def test_subject_preview_cannot_be_applied_to_another_grade(self):
        from subjects.subject_import import (
            SubjectImportError,
            load_subject_preview,
            sign_subject_preview,
        )

        subject_data = [{
            'name': 'Applied Sciences',
            'discipline': 'Technical & Applied',
        }]
        token = sign_subject_preview(self.grade, subject_data)
        another_grade = GradeLevel.objects.create(
            name='Grade 11',
            slug='grade-11',
            level='Senior Secondary',
        )

        with self.assertRaises(SubjectImportError):
            load_subject_preview(token, another_grade)


class CurriculumProgressTests(TestCase):
    def setUp(self):
        self.grade = GradeLevel.objects.create(
            name='Grade 6',
            slug='grade-6',
            level='Upper Primary',
        )
        self.discipline = Discipline.objects.create(
            name='Science',
            slug='science-g6',
        )
        self.subject = Subject.objects.create(
            name='Integrated Science',
            slug='integrated-science-g6',
            grade_level=self.grade,
            discipline=self.discipline,
        )
        from subjects.models import Strand, SubStrand

        self.strand = Strand.objects.create(
            name='Living Things',
            slug='living-things-g6',
            subject=self.subject,
            order=1,
        )
        self.sub_a = SubStrand.objects.create(
            name='Plants',
            slug='plants-g6',
            strand=self.strand,
            order=1,
        )
        self.sub_b = SubStrand.objects.create(
            name='Animals',
            slug='animals-g6',
            strand=self.strand,
            order=2,
        )
        self.admin = get_user_model().objects.create_user(
            phone='0755555510',
            password='1234',
            role=Role.ADMIN,
        )

    def test_progress_averages_substrand_completion(self):
        from core.models import Question
        from subjects.curriculum_progress import build_curriculum_progress_by_subject

        for index in range(7):
            Question.objects.create(
                quiz=f'Q plant {index}',
                difficulty='Easy',
                quiz_type='Multiple Choice',
                sub_strand=self.sub_a,
                score=1,
            )
        Question.objects.create(
            quiz='Q animal',
            difficulty='Easy',
            quiz_type='Multiple Choice',
            sub_strand=self.sub_b,
            score=1,
        )

        stats = build_curriculum_progress_by_subject([self.subject.pk])[self.subject.pk]
        self.assertEqual(stats['ready_count'], 1)
        self.assertEqual(stats['substrand_count'], 2)
        self.assertEqual(stats['question_count'], 8)
        # 100% + ~14% → ~57%
        self.assertEqual(stats['progress_pct'], 57)

    def test_subject_list_shows_progress_pct(self):
        from core.models import Question

        for index in range(7):
            Question.objects.create(
                quiz=f'Q open {index}',
                difficulty='Easy',
                quiz_type='OpenEnded',
                sub_strand=self.sub_a,
            )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('subjects:subject_list') + '?grade=grade-6')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Question bank progress')
        self.assertContains(response, '1/2 sub-strands at 7+ questions')
