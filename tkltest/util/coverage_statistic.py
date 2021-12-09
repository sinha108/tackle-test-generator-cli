'''

    CoverageStatistic class:
    A class that represent the compare between two coverage statistic of an app, package, class or method.
    it has four derived class:
    AppCoverageStatistic, PackageCoverageStatistic, ClassCoverageStatistic and MethodCoverageStatistic.
    Every class has a pointer to a parent, and a list of children.
    For example, ClassCoverageStatistic will have a pointer to PackageCoverageStatistic and list of MethodCoverageStatistic
    Basically, we get a tree of CoverageStatistic instances, with AppCoverageStatistic as a root.


    CoverageStatistic class is used to create a coverage diff html report between two test suits.
    the main input is two xml files, and the app .class files, and the output is an html compare directory.

    The information that we use in the xml look like:
    1. for each app/package/class/method, there is a summery of the form:
                        counter type="INSTRUCTION" missed="71" covered="994"/>
                        <counter type="BRANCH" missed="1" covered="17"/>
                        <counter type="LINE" missed="12" covered="201"/>
                        <counter type="COMPLEXITY" missed="4" covered="57"/>
                        <counter type="METHOD" missed="3" covered="49"/>
                        <counter type="CLASS" missed="0" covered="5"/>

    2. for every source line there is an entry of the form:
                        <line nr="16" mi="0" ci="2" mb="0" cb="0"/>


    CoverageStatistic holds a dict of counters, a counter per:
                'INSTRUCTION','BRANCH','COMPLEXITY','LINE','METHOD','CLASS'
    each counter holds:
    1. the total of covered/missed, the value that we read directly from the xml
    2. the diff between the test suits, which is calculated by processing the xml line coverage

    The main steps of the report creation:
    1. reading the XML files, generated by jacococli, build the tree, and update the counters with the total xml values.
    2. parse the .class files of the app, to get the source line numbers of each method
    3. iterating over the xml line information, and update only the 'LINE' counter:
                -which line was missed by both test suites,
                -which line was missed by first test suite ,
                -which line was missed by second test suite,
                -which line was not missed by any of the test suite,
        ( we can consider updating also 'METHOD' and 'CLASS' counters )
        ( we can consider updating also 'INSTRUCTION' and 'BRANCH' counters, but the result will not be accurate )
    4. building the html files. each CoverageStatistic is a line in the table. each counter is an entry in the table


'''




import os
from bs4 import BeautifulSoup
import sys

from tkltest.util import java_class_parser
from tkltest.util.logging_util import tkltest_status


class CoverageStatistic:
    counter_types = {'INSTRUCTION': {'name': 'Instructions', 'is_bar': False},
                     'BRANCH': {'name': 'Branches', 'is_bar': False},
                     'COMPLEXITY': {'name': 'Cxty', 'is_bar': False},
                     'LINE': {'name': 'Lines', 'is_bar': True},
                     'METHOD': {'name': 'Methods', 'is_bar': False},
                     'CLASS': {'name': 'Classes', 'is_bar': False}
                     }


    # These three variables are static - same values for all instances
    test_name1 = ''
    test_name2 = ''
    report_name = 'Tackle Coverage Compare Report'

    class Counter:
        def __init__(self, covered1, covered2, missed1, missed2):
            self.total_covered1 = covered1
            self.total_covered2 = covered2
            self.total_missed1 = missed1
            self.total_missed2 = missed2
            if self.total_covered1 + self.total_missed1 != self.total_covered2 + self.total_missed2:
                tkltest_status('fail to parse', error=True)  # todo
                sys.exit(1)
            self.total = self.total_covered1 + self.total_missed1
            self.missed_both = 0
            self.missed_only1 = 0
            self.missed_only2 = 0
            self.missed_none = 0


        #methods that translate a Counter to html code:
        @staticmethod
        def get_html_bar_segment(bar_scale, color, val):
            return '<img src = "jacoco-resources/' + color + 'bar.gif" width = "{}" height = "10" title = "{}" alt = "{}" />'.format(
                int(val / bar_scale), val, val)

        def get_html_coverage_compare(self):
            return '<td class="clr1"> {}% vs %{} </td>'.format(int(100 * self.total_covered1 / self.total),
                                                               int(100 * self.total_covered2 / self.total))

        def get_html_bar(self, max_val):
            bar_scale = max_val/100
            ibar = self.get_html_bar_segment(bar_scale, 'red', self.missed_both)
            ibar += self.get_html_bar_segment(bar_scale, 'yellow', self.missed_only1)
            ibar += self.get_html_bar_segment(bar_scale, 'blue', self.missed_only2)
            ibar += self.get_html_bar_segment(bar_scale, 'green', self.missed_none)
            ibar += self.get_html_coverage_compare()
            return '<td class="bar">' + ibar + '</td>'

        def get_html_coverage_diff(self):
            return '<td class="clr2"> both={} 1st={} 2nd={} none={}</td>'\
                    .format(self.missed_both, self.missed_only1,self.missed_only2, self.missed_none) + \
                   self.get_html_coverage_compare()

        def get_html_misses_diff(self):
            return '<td class="clr2"> {} vs {} </td>'.format(self.total_missed1, self.total_missed2) + \
                   '<td class="clr1"> {} </td>'.format(self.total)

        @staticmethod
        def get_html_na():
            return '<td class="bar"></td>' \
                   '<td class="clr1"> n/a </td>'

    def __init__(self, parent=None):
        self.name = ''
        self.counters = {}
        self.parent = parent
        self.children = []
        if self.parent:
            self.parent.children.append(self)

    def parse_xml(self, xml_entry1, xml_entry2):
        self.set_name(xml_entry1, xml_entry2)
        self.__update_xml_statistic(xml_entry1, xml_entry2)

    def __update_xml_statistic(self, xml_entry1, xml_entry2):
        '''
        Update the counters with the xml total values
        '''
        for coverage_type in self.counter_types.keys():
            coverage_counter1 = [counter for counter in xml_entry1 if 'type' in counter.attrib and counter.attrib['type'] == coverage_type]
            coverage_counter2 = [counter for counter in xml_entry2 if 'type' in counter.attrib and counter.attrib['type'] == coverage_type]
            if len(coverage_counter1) == 0 and len(coverage_counter2) == 0:
                continue
            if len(coverage_counter1) != 1 or len(coverage_counter2) != 1:
                tkltest_status('fail to parse', error=True)  # todo
                sys.exit(1)
            coverage_counter1 = coverage_counter1[0]
            coverage_counter2 = coverage_counter2[0]
            self.counters[coverage_type] = self.Counter(int(coverage_counter1.attrib['covered']),
                                                        int(coverage_counter2.attrib['covered']),
                                                        int(coverage_counter1.attrib['missed']),
                                                        int(coverage_counter2.attrib['missed']))

    def update_line_statistic(self, mi1, mi2, ci1, ci2):
        '''
        update the counters (only 'LINE' counter with the diff values, using the one line statistic)
        Args:
            mi1: number of missed instructions by the first test suit
            mi2: number of missed instructions by the first second suit
            ci1: number of covered instructions by the first test suit
            ci2: number of covered instructions by the first second suit

        Returns:

        '''
        self.counters['LINE'].missed_both += int(mi1) > 0 and int(mi2) > 0
        self.counters['LINE'].missed_none += int(mi1) == 0 and int(mi2) == 0
        self.counters['LINE'].missed_only1 += int(mi1) > 0 and int(mi2) == 0
        self.counters['LINE'].missed_only2 += int(mi1) == 0 and int(mi2) > 0

        '''
        the following relevant if we want to present the instruction as a bar 
        self.counters['INSTRUCTION'].missed_both += min([int(mi1), int(mi2)])
        self.counters['INSTRUCTION'].missed_none += min([int(ci1), int(ci2)])
        self.counters['INSTRUCTION'].missed_only1 += max([0, int(mi1) - int(mi2)])
        self.counters['INSTRUCTION'].missed_only2 += max([0, int(mi2) - int(mi1)])
        '''
        if self.parent:
            self.parent.update_line_statistic(mi1, mi2, ci1, ci2)

    def get_html_table_line(self, summarize=False):
        '''
        Convert the CoverageStatistic to an html row in the html table
        Args:
            summarize: true if it is the last row in the table (in this case we do not create a bar)

        Returns:
            html line - a row in the table
        '''
        line = ''
        for coverage_type, coverage_type_data in self.counter_types.items():
            if self.counters.get(coverage_type) and self.counters[coverage_type].total != 0:
                counter = self.counters[coverage_type]
                if coverage_type_data['is_bar']:
                    if not summarize:
                        # we normalize the bars with the largest bar
                        max_val = max([child.counters[coverage_type].total for child in self.parent.children if
                                       child.counters.get(coverage_type)])
                        line += counter.get_html_bar(max_val)
                    else:
                        line += counter.get_html_coverage_diff()
                else:
                    line += counter.get_html_misses_diff()
            else:
                line += self.Counter.get_html_na()
        return line

    def print_html(self, html_compare_dir, html1_dir, html2_dir):
        '''
        Convert the CoverageStatistic to an html file
        Args:
            html_compare_dir: the output directory
            html1_dir: the directory of the first suit
            html2_dir: the directory of the second suit
        '''

        if not len(self.counters):
            return
        html_file_name = self.get_html_file_name()

        '''
        reading the html files, that was generated by the jacoco cli.
        from these html files we :
        1. take the html original tables
        2. take the html links to other html files
        3. take the html head
        4. see if we need to correct the reference to the jacoco resources in the html table
        '''

        with open(html1_dir + os.sep + html_file_name) as html1_file:
            soup1 = BeautifulSoup(html1_file.read(), 'html.parser').html
        with open(html2_dir + os.sep + html_file_name) as html2_file:
            soup2 = BeautifulSoup(html2_file.read(), 'html.parser').html

        html_head = str(soup1.head)
        # taking the html links:
        html_tree_links = str(soup1.body.div).replace(str(soup1.body.div.find_all(class_='info')[0]), '')
        html_tree_links = html_tree_links.replace('JaCoCo Coverage Report', CoverageStatistic.report_name)

        html_title = '<h1>' + self.name + '</h1>'
        html_title += '<h1><span> First Test Directory: </span><span style="background-color:yellow"> ' + self.test_name1 + '</span></h1>'
        html_title += '<h1><span>Second Test Directory: </span><span style="background-color:cornflowerblue">' + self.test_name2 + '</span></h1>'

        html_table_titles = '<td class="sortable" id="a" onclick="toggleSort(this)">Element</td>'
        for coverage_type in self.counter_types.values():
            if coverage_type['is_bar']:
                html_table_titles += '<td class="down sortable bar" id="b" onclick="toggleSort(this)">Missed ' + coverage_type['name'] + '</td>'
                html_table_titles += '<td class="sortable ctr2" onclick="toggleSort(this)">Cov.</td>'
            else:
                html_table_titles += '<td class="sortable ctr1" onclick="toggleSort(this)">Missed</td>'
                html_table_titles += '<td class="sortable ctr2" onclick="toggleSort(this)">' + coverage_type['name'] + '</td>'

        html_table_head = '<thead><tr>' + html_table_titles + '</tr></thead>'


        html_table_foot = '<tfoot><tr><td>Total</td>' + self.get_html_table_line(summarize=True) + '</tr></tfoot>'

        html_table_body = '<tbody>'
        for child_statistic in self.children:
            if not len(child_statistic.counters):
                continue
            child_name = child_statistic.get_html_name()
            child_html_file = child_statistic.get_html_file_name()
            html_table_line = '<tr>'
            href = ''
            if child_html_file:
                href = ' href="' + child_html_file + '" class="' + child_statistic.get_html_el() + '"'
            html_table_line += '<td><a' + href + '>' + child_name + '</a></td>'
            html_table_line += child_statistic.get_html_table_line()
            html_table_line += '</tr>'
            html_table_body += html_table_line
        html_table_body += '</tbody>'


        table_legend = '<table>' \
                       '<tr><td class=bar>' + CoverageStatistic.Counter.get_html_bar_segment(1, 'red', 10) + '</td>' \
                       '<td> Missed by both test suits</td></tr>' \
                       '<tr><td class=bar>' + CoverageStatistic.Counter.get_html_bar_segment(1, 'yellow', 10) + '</td>' \
                       '<td> Missed by first test suit only</td></tr>' \
                       '<tr><td class=bar>' + CoverageStatistic.Counter.get_html_bar_segment(1, 'blue', 10) + '</td>' \
                       '<td> Missed by second test suit only</td></tr>' \
                       '<tr><td class=bar>' + CoverageStatistic.Counter.get_html_bar_segment(1, 'green', 10) + '</td>' \
                       '<td> Covered by both test suits</td></tr></table>'

        html_table = '<table class="coverage" cellspacing="0" id="coveragetable">'
        html_table += html_table_head
        html_table += html_table_foot
        html_table += html_table_body
        html_table += '</table>'
        html_table += table_legend

        if '../jacoco-resources' in html_head:
            html_table = html_table.replace('jacoco-resources', '../jacoco-resources')


        html_test1_text = '<h1>-----------------------------------------------------------------------------------------------------------</h1>'
        html_test1_text += '<h1><span> Report With </span><span style="background-color:yellow"> ' + self.test_name1 + '</span></h1>'
        html_test1_text += str(soup1.body.table)
        html_test2_text = '<h1>-----------------------------------------------------------------------------------------------------------</h1>'
        html_test2_text += '<h1><span> Report With </span><span style="background-color:cornflowerblue">' + self.test_name2 + '</span></h1>'
        html_test2_text += str(soup2.body.table)

        html_text = '<html>' + html_head
        html_text += '<body>'
        html_text += html_tree_links
        html_text += html_title
        html_text += html_table
        html_text += html_test1_text
        html_text += html_test2_text
        html_text += '</body></html>'

        with open(html_compare_dir + os.sep + html_file_name, mode='w') as new_html_file:
            new_html_file.write(html_text)


class MethodCoverageStatistic(CoverageStatistic):
    def __init__(self, cls):
        super().__init__(parent=cls)
        self.signature = ''
    def set_name(self, xml_entry1, xml_entry2):
        self.name = xml_entry1.attrib['name']
        if self.name != xml_entry2.attrib['name']:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)
        ''' the "desc" is in the form of:
        (full name parameters)full name return value
        for example:
        (ILjava/lang/String;Ljava/sql/Timestamp;)Ljava/lang/String;
        we will get a list of only the base name of the parameters, and drop the return value:
        parameters = ['Timestamp','String'] 
        '''
        parameters = xml_entry1.attrib['desc']
        self.signature = self.name + parameters
        if parameters != xml_entry2.attrib['desc']:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)
        parameters = parameters.strip("()").split(';')
        parameters.pop() # removing the return value
        parameters = [param.split('/').pop() for param in parameters]
        self.name = self.name + '(' + ', '.join(parameters) + ')'
        self.name = self.name.replace('<init>', self.parent.name)
        self.name = self.name.replace('<clinit>()', 'static {...}')

    def get_html_name(self):
        return self.name

    def get_html_file_name(self):
        return ''


class ClassCoverageStatistic(CoverageStatistic):

    def __init__(self, package):
        super().__init__(parent=package)
        self.file_name = ''

    def set_name(self, xml_entry1, xml_entry2):
        self.name = xml_entry1.attrib['name']
        if self.name != xml_entry2.attrib['name']:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)
        # removing the package name from the class name
        self.name = self.name.replace(self.parent.name + '/', '', 1)
        self.file_name = xml_entry1.attrib['sourcefilename']
        if self.file_name != xml_entry2.attrib['sourcefilename']:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)

    def get_html_name(self):
        return self.name

    def get_html_file_name(self):
        return self.name + '.html'

    def get_html_el(self):
        return 'el_class'


class PackageCoverageStatistic(CoverageStatistic):

    def __init__(self, app, monolith_app_path):
        super().__init__(parent=app)
        self.line_to_methods = {}
        self.monolith_app_path = monolith_app_path

    def set_name(self, xml_entry1, xml_entry2):
        self.name = xml_entry1.attrib['name']
        if self.name != xml_entry2.attrib['name']:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)

    def get_html_name(self):
        return self.name.replace('/', '.')

    def get_html_file_name(self):
        return self.get_html_name() + os.sep + 'index.html'

    def get_html_el(self):
        return 'el_package'

    def parse_class_file(self, current_class):
        '''
        this method parse of the .class files. it:
        1. call the parser
        2. try to eliminate methods that are in the .class files, but does not have CoverageStatistic instance
        (i.e. these methode was not on the xml file)
        3. update the dict line_to_methods, to be used when reading the lines info from the xml

        '''
        class_file_names = [path + os.sep + self.name + os.sep + current_class.name + '.class'
                            for path in self.monolith_app_path
                            if os.path.isfile(path + os.sep + self.name + os.sep + current_class.name + '.class')]
        if not len(class_file_names):
            print('didnt find .class file ')
            exit(1)  # todo
        class_file_name = class_file_names[0]

        '''the following code involve the .class parser.
            matching between the bytecode and the xml by name+desc 
            '''
        byte_code_data = java_class_parser.JavaClass.from_file(class_file_name)

        lines_tables = {}
        for byte_code_method in byte_code_data.methods:
            descriptor_index = byte_code_method.descriptor_index - 1
            name_index = byte_code_method.name_index - 1
            name = byte_code_data.constant_pool[name_index].cp_info.value
            desc = byte_code_data.constant_pool[descriptor_index].cp_info.value
            signature = name + desc
            code_attributes = [att for att in byte_code_method.attributes if att.name_as_str == 'Code']
            if(len(code_attributes)):
                lines_tables[signature] = code_attributes[0].info.attributes[0].info.line_number_table

        if not self.line_to_methods.get(current_class.file_name):
            self.line_to_methods[current_class.file_name] = {}
        for method in current_class.children:
            byte_code_lines_table = lines_tables[method.signature]
            for line_entry in byte_code_lines_table:
                if not self.line_to_methods[current_class.file_name].get(line_entry.line_number):
                    self.line_to_methods[current_class.file_name][line_entry.line_number] = set()
                self.line_to_methods[current_class.file_name][line_entry.line_number].add(method)

    def parse_sourcefile_xml(self, xml_entry1, xml_entry2):
        '''
        methods that iterate over the lines coverage data of a source file, and update the methods
        Args:
            xml_entry1/2: the xml file entry

        '''
        file_name, file_name2 = xml_entry1.attrib['name'], xml_entry2.attrib['name']
        if file_name != file_name2:
            tkltest_status('fail to parse', error=True)  # todo
            sys.exit(1)
        lines1, lines2 = xml_entry1.findall('line'), xml_entry2.findall('line')
        for line1, line2 in zip(lines1, lines2):
            line_number = int(line1.attrib['nr'])
            if line_number != int(line2.attrib['nr']):
                tkltest_status('fail to parse', error=True)  # todo
                sys.exit(1)
            mi1, mi2 = int(line1.attrib['mi']), int(line2.attrib['mi'])
            ci1, ci2 = int(line1.attrib['ci']), int(line2.attrib['ci'])
            if line_number not in self.line_to_methods[file_name].keys():
                tkltest_status('line number wo methods ' + file_name + str(line_number), error=True)  # todo
                #sys.exit(1)
            else:
                for method in self.line_to_methods[file_name][line_number]:
                    method.update_line_statistic(mi1, mi2, ci1, ci2)


class AppCoverageStatistic(CoverageStatistic):

    def __init__(self, test_name1, test_name2):
        super().__init__()
        CoverageStatistic.test_name1 = test_name1
        CoverageStatistic.test_name2 = test_name2

    def set_name(self, xml_entry1, xml_entry2):
        self.name = CoverageStatistic.report_name

    def get_html_file_name(self):
        return 'index.html'


